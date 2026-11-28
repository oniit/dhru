"""
Standalone 2-Way Full PTY Telegram Terminal Bot (1 static file).

Menjembatani chat privat Telegram Owner dengan sesi shell Linux interaktif (PTY)
secara real-time 2 arah di VPS. Dijalankan terpisah dari ``main.py`` menggunakan
token bot tersendiri agar tetap aktif meskipun bot utama sedang restart/crash.

Environment variables (.env):
  - TERMINAL_BOT_TOKEN : Token bot Telegram khusus terminal (wajib, dari @BotFather)
  - OWNER_ID           : Numeric Telegram User ID pemilik (wajib, sudah ada di .env)
  - TERMINAL_OWNER_IDS : (Opsional) Daftar ID pemilik dipisah koma jika >1; override OWNER_ID
  - TERMINAL_SHELL     : (Opsional) Path shell, default $SHELL atau /bin/bash
  - TERMINAL_WORKDIR   : (Opsional) Direktori awal shell, default direktori proyek
  - TERMINAL_COLS      : (Opsional) Lebar kolom PTY, default 100
  - TERMINAL_ROWS      : (Opsional) Tinggi baris PTY, default 36
"""

from __future__ import annotations

import asyncio
import codecs
from collections import deque
from dataclasses import dataclass
import html
import io
import logging
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time
from typing import Callable

try:
    import fcntl
    import pty
    import termios

    POSIX_PTY_AVAILABLE = True
except ImportError:
    fcntl = None  # type: ignore[assignment]
    pty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]
    POSIX_PTY_AVAILABLE = False

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("terminal_bot")

ROOT_DIR = Path(__file__).resolve().parent
MAX_PRE_HTML_CHARS = 3800
MASSIVE_OUTPUT_HTML_THRESHOLD = 15000
FLUSH_DEBOUNCE_SEC = 0.65
TAIL_LINES_AFTER_FILE = 25

_CSI_CURSOR_G_RE = re.compile(r"^(\d*)G$")
_CSI_CURSOR_C_RE = re.compile(r"^(\d*)C$")
_CSI_CURSOR_D_RE = re.compile(r"^(\d*)D$")


def load_env_file(env_path: Path) -> None:
    """Load .env using python-dotenv if available, or a minimal fallback parser."""
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except ImportError:
        pass

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        elif "#" in val:
            val = val.split("#", 1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = val


def _parse_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _parse_owner_ids() -> frozenset[int]:
    multi_raw = os.environ.get("TERMINAL_OWNER_IDS", "").strip()
    ids: set[int] = set()
    if multi_raw:
        for part in multi_raw.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                val = int(part)
                if val > 0:
                    ids.add(val)
    if not ids:
        single_raw = os.environ.get("OWNER_ID", "").strip()
        if single_raw.lstrip("-").isdigit():
            val = int(single_raw)
            if val > 0:
                ids.add(val)
    return frozenset(ids)


def _default_shell() -> str:
    configured = os.environ.get("TERMINAL_SHELL", "").strip()
    if configured:
        return configured
    env_shell = os.environ.get("SHELL", "").strip()
    if env_shell and Path(env_shell).exists():
        return env_shell
    if Path("/bin/bash").exists():
        return "/bin/bash"
    return "/bin/sh"


@dataclass(frozen=True)
class TerminalConfig:
    """Konfigurasi runtime untuk bot terminal PTY."""

    bot_token: str
    allowed_owners: frozenset[int]
    shell: str
    workdir: str
    cols: int
    rows: int

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "TerminalConfig":
        load_env_file(env_path or (ROOT_DIR / ".env"))
        raw_token = os.environ.get("TERMINAL_BOT_TOKEN", "").strip()
        token = raw_token.split("#", 1)[0].strip() if raw_token else ""
        workdir = os.environ.get("TERMINAL_WORKDIR", "").strip() or str(ROOT_DIR)
        return cls(
            bot_token=token,
            allowed_owners=_parse_owner_ids(),
            shell=_default_shell(),
            workdir=workdir,
            cols=_parse_int_env("TERMINAL_COLS", 100, minimum=20),
            rows=_parse_int_env("TERMINAL_ROWS", 36, minimum=10),
        )


def is_authorized(update: Update, allowed_owners: frozenset[int]) -> bool:
    """Tolak akses dari non-owner atau dari luar private chat."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if chat.type != "private":
        return False
    return user.id in allowed_owners


class TerminalBuffer:
    """Buffer layar teks terminal yang membersihkan kode ANSI dan mensimulasikan CR/BS/CSI."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.cur_chars: list[str] = []
        self.cursor: int = 0
        self._esc_buf: str = ""

    def clear(self) -> None:
        self.lines.clear()
        self.cur_chars.clear()
        self.cursor = 0
        self._esc_buf = ""

    def feed(self, text: str) -> None:
        for ch in text:
            if self._esc_buf:
                self._consume_escape_char(ch)
                continue
            if ch == "\x1b":
                self._esc_buf = ch
            elif ch == "\r":
                self.cursor = 0
            elif ch == "\n":
                self.lines.append("".join(self.cur_chars))
                self.cur_chars.clear()
                self.cursor = 0
            elif ch == "\b":
                self.cursor = max(0, self.cursor - 1)
            elif ch == "\t":
                spaces = 8 - (self.cursor % 8)
                for _ in range(spaces):
                    self._write_char(" ")
            elif ord(ch) < 32 or ord(ch) == 127:
                continue
            else:
                self._write_char(ch)

    def _write_char(self, ch: str) -> None:
        if self.cursor < len(self.cur_chars):
            self.cur_chars[self.cursor] = ch
        elif self.cursor == len(self.cur_chars):
            self.cur_chars.append(ch)
        else:
            self.cur_chars.extend(" " * (self.cursor - len(self.cur_chars)))
            self.cur_chars.append(ch)
        self.cursor += 1

    def _consume_escape_char(self, ch: str) -> None:
        self._esc_buf += ch
        buf = self._esc_buf
        if len(buf) > 4096:
            self._esc_buf = ""
            return

        if len(buf) == 2:
            if ch in "[]PX^_()*+#% ":
                return
            self._esc_buf = ""
            return

        prefix = buf[1]
        if prefix == "[":
            if 0x40 <= ord(ch) <= 0x7E:
                self._handle_csi(buf[2:])
                self._esc_buf = ""
            return
        if prefix == "]":
            if ch == "\x07" or buf.endswith("\x1b\\"):
                self._esc_buf = ""
            return
        if prefix in "PX^_":
            if ch == "\x07" or buf.endswith("\x1b\\"):
                self._esc_buf = ""
            return
        if prefix in "()*+#% " and len(buf) >= 3:
            self._esc_buf = ""

    def _handle_csi(self, seq: str) -> None:
        if seq in ("K", "0K"):
            self.cur_chars = self.cur_chars[: self.cursor]
            return
        if seq == "2K":
            self.cur_chars.clear()
            return
        if seq == "1K":
            limit = min(self.cursor, len(self.cur_chars))
            for i in range(limit):
                self.cur_chars[i] = " "
            return
        if seq in ("2J", "3J"):
            self.lines.clear()
            self.cur_chars.clear()
            self.cursor = 0
            return

        if m := _CSI_CURSOR_G_RE.match(seq):
            col = int(m.group(1) or "1")
            self.cursor = max(0, col - 1)
            return
        if m := _CSI_CURSOR_C_RE.match(seq):
            step = int(m.group(1) or "1")
            self.cursor += step
            return
        if m := _CSI_CURSOR_D_RE.match(seq):
            step = int(m.group(1) or "1")
            self.cursor = max(0, self.cursor - step)

    def render(self) -> str:
        cur = "".join(self.cur_chars)
        if not self.lines:
            return cur
        return "\n".join(self.lines) + "\n" + cur

    def replace_text(self, text: str) -> None:
        self.lines.clear()
        self.cur_chars.clear()
        self.cursor = 0
        if text:
            parts = text.split("\n")
            self.lines.extend(parts[:-1])
            self.cur_chars = list(parts[-1])
            self.cursor = len(self.cur_chars)

    def replace_with_tail(self, max_lines: int = TAIL_LINES_AFTER_FILE, max_chars: int = 1800) -> None:
        text = self.render()
        tail_lines = text.splitlines()[-max_lines:]
        tail = "\n".join(tail_lines)
        if len(tail) > max_chars:
            tail = tail[-max_chars:]
        self.replace_text(tail)


def split_for_telegram_html(text: str, max_html_len: int = MAX_PRE_HTML_CHARS) -> list[str]:
    """Pecah teks menjadi beberapa potongan agar hasil html.escape <= max_html_len."""
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(html.escape(remaining)) <= max_html_len:
            chunks.append(remaining)
            break

        # Cari panjang karakter mentah terbesar yang hasil escape-nya muat
        lo, hi = 1, min(len(remaining), max_html_len)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if len(html.escape(remaining[:mid])) <= max_html_len:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        # Prioritaskan potong di batas baris baru agar rapi
        nl = remaining.rfind("\n", max(1, best // 2), best + 1)
        cut = nl + 1 if nl > 0 else best
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    return chunks


def _build_control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⌃C", callback_data="pty:ctrlc"),
                InlineKeyboardButton("↵ Enter", callback_data="pty:enter"),
                InlineKeyboardButton("⇥ Tab", callback_data="pty:tab"),
                InlineKeyboardButton("⌃D", callback_data="pty:ctrld"),
                InlineKeyboardButton("🔄 Reset", callback_data="pty:reset"),
            ]
        ]
    )


class PtyShell:
    """Mengelola proses shell POSIX di dalam PTY dan streaming pembacaannya."""

    def __init__(
        self,
        config: TerminalConfig,
        on_output: Callable[[str], None],
        on_exit: Callable[[int | None], None],
    ) -> None:
        self.config = config
        self._on_output = on_output
        self._on_exit = on_exit
        self.master_fd: int | None = None
        self.proc: subprocess.Popen[bytes] | None = None
        self.cols = config.cols
        self.rows = config.rows
        self.started_at: float = 0.0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reader_registered = False

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None and self.master_fd is not None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not POSIX_PTY_AVAILABLE:
            raise RuntimeError("Full PTY membutuhkan OS POSIX/Linux (modul pty/termios/fcntl tidak tersedia di Windows).")
        if self.is_alive:
            return

        self._loop = loop
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        master_fd, slave_fd = pty.openpty()
        self._set_winsize(slave_fd, self.cols, self.rows)

        child_env = os.environ.copy()
        child_env["TERM"] = "xterm-256color"
        child_env["COLUMNS"] = str(self.cols)
        child_env["LINES"] = str(self.rows)
        child_env.setdefault("LANG", "C.UTF-8")
        child_env.setdefault("LC_ALL", "C.UTF-8")
        child_env["PYTHONUNBUFFERED"] = "1"
        child_env.setdefault("PAGER", "cat")
        child_env.setdefault("GIT_PAGER", "cat")
        child_env.setdefault("SYSTEMD_PAGER", "cat")

        def _setup_controlling_tty() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        workdir = self.config.workdir if Path(self.config.workdir).is_dir() else str(ROOT_DIR)
        try:
            proc = subprocess.Popen(
                [self.config.shell],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=workdir,
                env=child_env,
                preexec_fn=_setup_controlling_tty,
                close_fds=True,
            )
        except Exception:
            os.close(master_fd)
            os.close(slave_fd)
            raise

        os.close(slave_fd)
        os.set_blocking(master_fd, False)
        self.master_fd = master_fd
        self.proc = proc
        self.started_at = time.time()
        loop.add_reader(master_fd, self._handle_readable)
        self._reader_registered = True

    def _set_winsize(self, fd: int, cols: int, rows: int) -> None:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def resize(self, cols: int, rows: int) -> None:
        self.cols = max(20, min(300, cols))
        self.rows = max(10, min(120, rows))
        if self.master_fd is not None and POSIX_PTY_AVAILABLE:
            self._set_winsize(self.master_fd, self.cols, self.rows)

    def write(self, data: bytes) -> None:
        if self.master_fd is None:
            raise RuntimeError("PTY belum berjalan.")
        view = memoryview(data)
        total = 0
        while total < len(view):
            try:
                written = os.write(self.master_fd, view[total:])
                if written <= 0:
                    break
                total += written
            except BlockingIOError:
                time.sleep(0.01)

    def _handle_readable(self) -> None:
        if self.master_fd is None:
            return
        chunks: list[bytes] = []
        eof = False
        read_bytes = 0
        while read_bytes < 262144:
            try:
                data = os.read(self.master_fd, 65536)
                if not data:
                    eof = True
                    break
                chunks.append(data)
                read_bytes += len(data)
            except BlockingIOError:
                break
            except OSError:
                eof = True
                break

        if chunks:
            text = self._decoder.decode(b"".join(chunks), final=eof)
            if text:
                self._on_output(text)
        elif eof:
            tail = self._decoder.decode(b"", final=True)
            if tail:
                self._on_output(tail)

        if eof:
            self._cleanup_after_eof()

    def _cleanup_after_eof(self) -> None:
        self._unregister_reader()
        code: int | None = None
        if self.proc is not None:
            try:
                code = self.proc.poll()
                if code is None:
                    code = self.proc.wait(timeout=0.5)
            except Exception:
                code = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self.proc = None
        self._on_exit(code)

    def _unregister_reader(self) -> None:
        if self._reader_registered and self._loop is not None and self.master_fd is not None:
            try:
                self._loop.remove_reader(self.master_fd)
            except Exception:
                pass
        self._reader_registered = False

    def stop(self) -> None:
        self._unregister_reader()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self.proc = None


class TerminalBridge:
    """Mengkoordinasikan PTY session dengan streaming pesan 2 arah di Telegram."""

    def __init__(self, config: TerminalConfig) -> None:
        self.config = config
        self.buffer = TerminalBuffer()
        self._incoming: deque[str] = deque()
        self._io_lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._application: Application | None = None
        self._active_chat_id: int | None = None
        self._active_msg: Message | None = None
        self._last_sent_html: str = ""
        self._session_gen: int = 0
        self._exit_notified_gen: int = -1
        self.shell = PtyShell(
            config=config,
            on_output=self._on_pty_output,
            on_exit=self._on_pty_exit,
        )

    def bind_application(self, application: Application) -> None:
        self._application = application

    def ensure_session(self, chat_id: int) -> None:
        self._active_chat_id = chat_id
        if not self.shell.is_alive:
            self._session_gen += 1
            self.shell.start(asyncio.get_running_loop())

    def _on_pty_output(self, text: str) -> None:
        self._incoming.append(text)
        self._schedule_flush()

    def _on_pty_exit(self, code: int | None) -> None:
        gen = self._session_gen
        if self._exit_notified_gen == gen:
            return
        self._exit_notified_gen = gen
        asyncio.create_task(self._handle_exit_notification(gen, code))

    async def _handle_exit_notification(self, session_gen: int, code: int | None) -> None:
        await asyncio.sleep(0.15)
        async with self._io_lock:
            if session_gen != self._session_gen:
                return
            self._drain_incoming_into_buffer()
            if self.buffer.render().strip():
                await self._flush_locked()
            if self._application and self._active_chat_id:
                await self._clear_active_markup()
                self._active_msg = None
                self._last_sent_html = ""
                self.buffer.clear()
                try:
                    await self._application.bot.send_message(
                        chat_id=self._active_chat_id,
                        text=(
                            f"⚠️ <b>Sesi shell berakhir</b> (exit code: <code>{code}</code>).\n"
                            "Kirim perintah apa saja atau /reset untuk membuka shell baru."
                        ),
                        parse_mode="HTML",
                    )
                except TelegramError as exc:
                    log.warning("Gagal mengirim notifikasi exit shell: %s", exc)

    def _schedule_flush(self) -> None:
        if self._flush_task and not self._flush_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._debounced_flush())
        except RuntimeError:
            pass

    async def _debounced_flush(self) -> None:
        await asyncio.sleep(FLUSH_DEBOUNCE_SEC)
        await self.flush_output(force=False)
        if self._incoming:
            self._schedule_flush()

    def _drain_incoming_into_buffer(self) -> None:
        while self._incoming:
            self.buffer.feed(self._incoming.popleft())

    async def _clear_active_markup(self) -> None:
        if self._active_msg is not None:
            try:
                await self._active_msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    async def send_input(
        self,
        chat_id: int,
        data: bytes,
        *,
        detach_message: bool = True,
    ) -> None:
        async with self._io_lock:
            self._active_chat_id = chat_id
            self._drain_incoming_into_buffer()
            if self.buffer.render().strip():
                await self._flush_locked()
            if detach_message:
                await self._clear_active_markup()
                self._active_msg = None
                self._last_sent_html = ""
                self.buffer.clear()
            self.ensure_session(chat_id)
            self.shell.write(data)

    async def reset_session(self, chat_id: int) -> None:
        async with self._io_lock:
            await self._clear_active_markup()
            self._incoming.clear()
            self.buffer.clear()
            self._active_msg = None
            self._last_sent_html = ""
            self._session_gen += 1
            self.shell.stop()
            self._active_chat_id = chat_id
            self.shell.start(asyncio.get_running_loop())

    async def flush_output(self, *, force: bool = False) -> None:
        async with self._io_lock:
            self._drain_incoming_into_buffer()
            if not force and not self.buffer.render().strip():
                return
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._application or not self._active_chat_id:
            return
        rendered = self.buffer.render()
        if not rendered.strip():
            return

        escaped_full = html.escape(rendered)
        if len(escaped_full) > MASSIVE_OUTPUT_HTML_THRESHOLD:
            await self._send_massive_output_as_file(rendered)
            rendered = self.buffer.render()
            if not rendered.strip():
                return

        chunks = [c for c in split_for_telegram_html(rendered, MAX_PRE_HTML_CHARS) if c.strip()]
        if not chunks:
            return

        # Finalize older overflow chunks first without buttons
        for old_chunk in chunks[:-1]:
            chunk_html = f"<pre>{html.escape(old_chunk)}</pre>"
            await self._send_or_edit_active(chunk_html, with_keyboard=False)
            self._active_msg = None
            self._last_sent_html = ""

        # Last chunk becomes the active interactive tail message
        tail_chunk = chunks[-1]
        tail_html = f"<pre>{html.escape(tail_chunk)}</pre>"
        await self._send_or_edit_active(tail_html, with_keyboard=True)

        # Keep only the active tail inside TerminalBuffer
        if len(chunks) > 1:
            self.buffer.replace_text(tail_chunk)

    async def _send_massive_output_as_file(self, rendered: str) -> None:
        assert self._application is not None and self._active_chat_id is not None
        await self._clear_active_markup()
        self._active_msg = None
        self._last_sent_html = ""
        bio = io.BytesIO(rendered.encode("utf-8", errors="replace"))
        bio.name = "terminal_output.txt"
        await self._call_telegram_with_retry(
            lambda: self._application.bot.send_document(  # type: ignore[union-attr]
                chat_id=self._active_chat_id,  # type: ignore[arg-type]
                document=bio,
                caption="📄 Output panjang dikirim sebagai berkas; menampilkan baris terakhir di bawah.",
            )
        )
        self.buffer.replace_with_tail()

    async def _send_or_edit_active(self, text_html: str, *, with_keyboard: bool) -> None:
        assert self._application is not None and self._active_chat_id is not None
        markup = _build_control_keyboard() if with_keyboard else None

        if self._active_msg is not None:
            if text_html == self._last_sent_html and with_keyboard:
                return
            try:
                await self._call_telegram_with_retry(
                    lambda: self._active_msg.edit_text(  # type: ignore[union-attr]
                        text_html,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                )
                self._last_sent_html = text_html
                return
            except BadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
                self._active_msg = None
            except TelegramError:
                self._active_msg = None

        msg = await self._call_telegram_with_retry(
            lambda: self._application.bot.send_message(  # type: ignore[union-attr]
                chat_id=self._active_chat_id,  # type: ignore[arg-type]
                text=text_html,
                parse_mode="HTML",
                reply_markup=markup,
            )
        )
        self._active_msg = msg
        self._last_sent_html = text_html

    async def _call_telegram_with_retry(self, fn):
        for attempt in range(3):
            try:
                return await fn()
            except RetryAfter as exc:
                wait_sec = float(exc.retry_after) + 0.5
                log.warning("Telegram FloodWait %.1fs", wait_sec)
                await asyncio.sleep(wait_sec)
            except BadRequest:
                raise
            except TelegramError as exc:
                if attempt == 2:
                    raise
                log.warning("TelegramError (%s), retry...", exc)
                await asyncio.sleep(1.0)

    async def shutdown(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self.shell.stop()


def build_application(config: TerminalConfig) -> Application:
    """Bangun Telegram Application beserta seluruh handler PTY 2 arah."""
    bridge = TerminalBridge(config)

    async def post_init(app: Application) -> None:
        bridge.bind_application(app)
        log.info(
            "Terminal PTY bot siap. Owners=%s Shell=%s Workdir=%s",
            sorted(config.allowed_owners),
            config.shell,
            config.workdir,
        )

    async def post_shutdown(_app: Application) -> None:
        await bridge.shutdown()

    async def guard(update: Update) -> bool:
        if is_authorized(update, config.allowed_owners):
            return True
        uid = update.effective_user.id if update.effective_user else None
        cid = update.effective_chat.id if update.effective_chat else None
        log.warning("Akses ditolak untuk user=%s chat=%s", uid, cid)
        return False

    async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.effective_chat or not update.message:
            return
        try:
            bridge.ensure_session(update.effective_chat.id)
        except Exception as exc:
            await update.message.reply_text(f"❌ Gagal memulai PTY: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")
            return

        status = f"PID <code>{bridge.shell.proc.pid}</code>" if bridge.shell.proc else "aktif"
        await update.message.reply_text(
            "🖥️ <b>VPS Full PTY Terminal Siap (2 Arah)</b>\n"
            f"• Status shell: {status} (<code>{html.escape(config.shell)}</code>)\n"
            f"• Workdir: <code>{html.escape(config.workdir)}</code>\n\n"
            "<b>Cara pakai:</b>\n"
            "• Kirim teks apa saja untuk mengirim perintah atau membalas prompt interaktif (<code>[y/N]</code>, REPL, dll).\n"
            "• <code>/secret &lt;teks&gt;</code> — Kirim password/token lalu hapus pesan chat Anda.\n"
            "• <code>/raw &lt;teks&gt;</code> — Kirim karakter persis tanpa Enter.\n"
            "• <code>/send &lt;teks&gt;</code> — Kirim teks apa adanya + Enter (termasuk yang diawali <code>/</code>).\n"
            "• <code>/ctrlc</code>, <code>/ctrld</code>, <code>/ctrlz</code>, <code>/enter</code>, <code>/tab</code>, <code>/esc</code>\n"
            "• <code>/status</code>, <code>/resize &lt;cols&gt; &lt;rows&gt;</code>, <code>/reset</code>",
            parse_mode="HTML",
        )

    async def _send_bytes(update: Update, data: bytes, label: str = "") -> None:
        if not await guard(update) or not update.effective_chat or not update.message:
            return
        try:
            await bridge.send_input(update.effective_chat.id, data, detach_message=True)
        except Exception as exc:
            await update.message.reply_text(f"❌ Gagal mengirim {label or 'input'}: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")

    async def cmd_ctrlc(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\x03", "Ctrl+C")

    async def cmd_ctrld(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\x04", "Ctrl+D")

    async def cmd_ctrlz(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\x1a", "Ctrl+Z")

    async def cmd_enter(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\r", "Enter")

    async def cmd_tab(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\t", "Tab")

    async def cmd_esc(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await _send_bytes(update, b"\x1b", "Esc")

    def _extract_command_payload(text: str) -> str:
        idx = text.find(" ")
        return text[idx + 1 :] if idx != -1 else ""

    async def cmd_raw(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.message:
            return
        payload = _extract_command_payload(update.message.text or "")
        if not payload:
            await update.message.reply_text("Format: <code>/raw &lt;teks&gt;</code>", parse_mode="HTML")
            return
        await _send_bytes(update, payload.encode("utf-8"), "raw")

    async def cmd_send(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.message:
            return
        payload = _extract_command_payload(update.message.text or "")
        await _send_bytes(update, (payload + "\n").encode("utf-8"), "send")

    async def cmd_secret(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.effective_chat or not update.message:
            return
        secret_val = _extract_command_payload(update.message.text or "")
        try:
            await update.message.delete()
        except Exception:
            pass
        if not secret_val:
            await update.effective_chat.send_message("Format: <code>/secret &lt;password_atau_input&gt;</code>", parse_mode="HTML")
            return
        try:
            await bridge.send_input(update.effective_chat.id, (secret_val + "\n").encode("utf-8"), detach_message=True)
        except Exception as exc:
            await update.effective_chat.send_message(f"❌ Gagal mengirim secret: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")

    async def cmd_reset(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.effective_chat or not update.message:
            return
        try:
            await bridge.reset_session(update.effective_chat.id)
            await update.message.reply_text("🔄 Sesi shell PTY di-reset dan dimulai ulang.")
        except Exception as exc:
            await update.message.reply_text(f"❌ Gagal reset PTY: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")

    async def cmd_status(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.message:
            return
        alive = bridge.shell.is_alive
        pid = bridge.shell.proc.pid if bridge.shell.proc else "-"
        uptime = f"{int(time.time() - bridge.shell.started_at)}s" if alive else "-"
        await update.message.reply_text(
            "📊 <b>Status Terminal PTY</b>\n"
            f"• Alive: <code>{alive}</code>\n"
            f"• PID: <code>{pid}</code>\n"
            f"• Uptime: <code>{uptime}</code>\n"
            f"• Ukuran: <code>{bridge.shell.cols}x{bridge.shell.rows}</code>\n"
            f"• Shell: <code>{html.escape(config.shell)}</code>",
            parse_mode="HTML",
        )

    async def cmd_resize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.message:
            return
        if len(context.args) != 2 or not all(a.isdigit() for a in context.args):
            await update.message.reply_text("Format: <code>/resize &lt;cols&gt; &lt;rows&gt;</code> (contoh: <code>/resize 120 40</code>)", parse_mode="HTML")
            return
        cols, rows = int(context.args[0]), int(context.args[1])
        bridge.shell.resize(cols, rows)
        await update.message.reply_text(f"📐 Ukuran PTY diatur ke <code>{bridge.shell.cols}x{bridge.shell.rows}</code>.", parse_mode="HTML")

    async def on_text(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update) or not update.effective_chat or not update.message:
            return
        text = update.message.text
        if text is None:
            return
        await _send_bytes(update, (text + "\n").encode("utf-8"), "teks")

    async def on_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        if not await guard(update):
            await query.answer("Tidak diizinkan.", show_alert=True)
            return
        if not update.effective_chat:
            return

        action = query.data or ""
        control_map = {
            "pty:ctrlc": (b"\x03", "⌃C dikirim"),
            "pty:enter": (b"\r", "↵ Enter dikirim"),
            "pty:tab": (b"\t", "⇥ Tab dikirim"),
            "pty:ctrld": (b"\x04", "⌃D dikirim"),
        }
        try:
            if action == "pty:reset":
                await bridge.reset_session(update.effective_chat.id)
                await query.answer("🔄 Shell di-reset")
                return
            if action in control_map:
                payload, label = control_map[action]
                await bridge.send_input(update.effective_chat.id, payload, detach_message=False)
                await query.answer(label)
                return
            await query.answer()
        except Exception as exc:
            await query.answer(f"Gagal: {exc}", show_alert=True)

    app = (
        Application.builder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler(["ctrlc", "c"], cmd_ctrlc))
    app.add_handler(CommandHandler(["ctrld", "d"], cmd_ctrld))
    app.add_handler(CommandHandler(["ctrlz", "z"], cmd_ctrlz))
    app.add_handler(CommandHandler("enter", cmd_enter))
    app.add_handler(CommandHandler("tab", cmd_tab))
    app.add_handler(CommandHandler("esc", cmd_esc))
    app.add_handler(CommandHandler("raw", cmd_raw))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler(["secret", "pass"], cmd_secret))
    app.add_handler(CommandHandler(["reset", "restart_shell"], cmd_reset))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("resize", cmd_resize))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^pty:"))
    app.add_handler(MessageHandler(filters.TEXT, on_text))
    return app


def main() -> None:
    config = TerminalConfig.from_env()
    if not config.bot_token:
        raise SystemExit("TERMINAL_BOT_TOKEN kosong. Tambahkan TERMINAL_BOT_TOKEN ke file .env.")
    if not config.allowed_owners:
        raise SystemExit("OWNER_ID / TERMINAL_OWNER_IDS kosong. Wajib isi numeric Telegram user ID di .env.")
    if not POSIX_PTY_AVAILABLE:
        raise SystemExit("Script ini harus dijalankan di Linux/POSIX VPS yang mendukung modul pty/termios/fcntl.")

    app = build_application(config)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
