import asyncio
import html
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

import terminal_bot


def _make_update(text: str, user_id: int = 999999, chat_type: str = "private") -> Update:
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    chat = MagicMock(spec=Chat)
    chat.id = user_id if chat_type == "private" else -100123456
    chat.type = chat_type
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.chat_id = chat.id
    msg.chat = chat
    msg.from_user = user
    msg.reply_text = AsyncMock()
    msg.delete = AsyncMock()
    update.effective_user = user
    update.effective_chat = chat
    update.message = msg
    update.callback_query = None
    return update


def test_terminal_buffer_ansi_cr_bs_and_split_escape():
    buf = terminal_bot.TerminalBuffer()
    # Title OSC + colors + split CSI sequence across two feed() calls
    buf.feed("\x1b]0;root@vps: ~/dhru\x07\x1b[32mhello\x1b[0")
    buf.feed("m world\r\n")
    # Progress bar overwrite with \r and \x1b[K
    buf.feed("Progress 10%\rProgress 100%\x1b[K\n")
    # Backspace + tab
    buf.feed("ab\bc\tX")

    assert buf.render() == "hello world\nProgress 100%\nac      X"


def test_terminal_buffer_clear_screen_and_tail():
    buf = terminal_bot.TerminalBuffer()
    buf.feed("old line\n\x1b[2Jfresh")
    assert buf.render() == "fresh"

    buf2 = terminal_bot.TerminalBuffer()
    buf2.feed("\n".join(f"line {i}" for i in range(50)))
    buf2.replace_with_tail(max_lines=5, max_chars=500)
    assert buf2.render() == "\n".join(f"line {i}" for i in range(45, 50))


def test_split_for_telegram_html_respects_escape_expansion():
    raw = ("<script>&" * 300) + "\n" + ("normal line\n" * 50)
    chunks = terminal_bot.split_for_telegram_html(raw, max_html_len=400)
    assert len(chunks) > 1
    assert "".join(chunks) == raw
    for chunk in chunks:
        assert len(html.escape(chunk)) <= 400


def test_config_from_env_and_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TERMINAL_BOT_TOKEN=12345:TEST_TOKEN # inline comment\n"
        "OWNER_ID=777888\n"
        "TERMINAL_COLS=120\n"
        "TERMINAL_ROWS=40\n",
        encoding="utf-8",
    )
    for k in ("TERMINAL_BOT_TOKEN", "OWNER_ID", "TERMINAL_OWNER_IDS", "TERMINAL_COLS", "TERMINAL_ROWS"):
        monkeypatch.delenv(k, raising=False)

    cfg = terminal_bot.TerminalConfig.from_env(env_file)
    assert cfg.bot_token == "12345:TEST_TOKEN"
    assert cfg.allowed_owners == frozenset({777888})
    assert cfg.cols == 120
    assert cfg.rows == 40

    assert terminal_bot.is_authorized(_make_update("ls", user_id=777888, chat_type="private"), cfg.allowed_owners) is True
    assert terminal_bot.is_authorized(_make_update("ls", user_id=111222, chat_type="private"), cfg.allowed_owners) is False
    assert terminal_bot.is_authorized(_make_update("ls", user_id=777888, chat_type="group"), cfg.allowed_owners) is False

    # Multi-owner override
    monkeypatch.setenv("TERMINAL_OWNER_IDS", "111, 222")
    cfg2 = terminal_bot.TerminalConfig.from_env(env_file)
    assert cfg2.allowed_owners == frozenset({111, 222})


def test_bridge_streaming_detach_massive_and_exit_guard():
    async def _run() -> None:
        cfg = terminal_bot.TerminalConfig(
            bot_token="123:ABC",
            allowed_owners=frozenset({42}),
            shell="/bin/bash",
            workdir=".",
            cols=100,
            rows=36,
        )
        bridge = terminal_bot.TerminalBridge(cfg)
        app = MagicMock()
        sent_msg = MagicMock(spec=Message)
        sent_msg.edit_text = AsyncMock()
        sent_msg.edit_reply_markup = AsyncMock()
        app.bot = MagicMock()
        app.bot.send_message = AsyncMock(return_value=sent_msg)
        app.bot.send_document = AsyncMock()
        bridge.bind_application(app)

        fake_shell = MagicMock()
        fake_shell.is_alive = True
        fake_shell.write = MagicMock()
        fake_shell.start = MagicMock()
        fake_shell.stop = MagicMock()
        bridge.shell = fake_shell

        # 1. Stream output chunk -> sends message
        bridge._active_chat_id = 42
        bridge._on_pty_output("Continue? [Y/n] ")
        await bridge.flush_output()
        app.bot.send_message.assert_awaited_once()
        assert "Continue? [Y/n]" in app.bot.send_message.call_args.kwargs["text"]

        # 2. Additional output -> edits active message
        bridge._on_pty_output("waiting")
        await bridge.flush_output()
        sent_msg.edit_text.assert_awaited_once()

        # 3. User sends input -> detaches old message so reply appears below
        await bridge.send_input(42, b"Y\n", detach_message=True)
        fake_shell.write.assert_called_with(b"Y\n")
        assert bridge._active_msg is None

        # 4. Massive output -> sends document + tail message
        app.bot.send_message.reset_mock()
        bridge._on_pty_output("x\n" * 10000)
        await bridge.flush_output()
        app.bot.send_document.assert_awaited_once()
        app.bot.send_message.assert_awaited_once()

        # 5. Stale exit notification after reset does not clear new session
        app.bot.send_message.reset_mock()
        stale_gen = bridge._session_gen
        await bridge.reset_session(42)
        await bridge._handle_exit_notification(stale_gen, 0)
        app.bot.send_message.assert_not_awaited()

        await bridge.shutdown()

    asyncio.run(_run())


def test_application_handlers_routing_and_secret():
    async def _run() -> None:
        cfg = terminal_bot.TerminalConfig(
            bot_token="123:ABC",
            allowed_owners=frozenset({42}),
            shell="/bin/bash",
            workdir=".",
            cols=100,
            rows=36,
        )
        with patch.object(terminal_bot, "PtyShell") as MockShellCls:
            mock_shell = MagicMock()
            mock_shell.is_alive = True
            mock_shell.cols = 100
            mock_shell.rows = 36
            mock_shell.started_at = 0.0
            mock_shell.proc = MagicMock(pid=1234)
            MockShellCls.return_value = mock_shell

            app = terminal_bot.build_application(cfg)
            handlers = app.handlers[0]

            # Find handlers by callback name / type
            by_name = {}
            for h in handlers:
                cb = h.callback
                by_name[cb.__name__] = h

            # Unauthorized user is ignored completely
            unauth_upd = _make_update("rm -rf /", user_id=123)
            await by_name["on_text"].callback(unauth_upd, MagicMock())
            mock_shell.write.assert_not_called()

            # Authorized plain text (even path starting with '/') -> sent with \n
            ok_upd = _make_update("/bin/ls -la", user_id=42)
            await by_name["on_text"].callback(ok_upd, MagicMock())
            mock_shell.write.assert_called_with(b"/bin/ls -la\n")

            # /raw preserves spaces and omits newline
            raw_upd = _make_update("/raw q", user_id=42)
            await by_name["cmd_raw"].callback(raw_upd, MagicMock())
            mock_shell.write.assert_called_with(b"q")

            # /send sends literal /start
            send_upd = _make_update("/send /start", user_id=42)
            await by_name["cmd_send"].callback(send_upd, MagicMock())
            mock_shell.write.assert_called_with(b"/start\n")

            # /secret deletes user message and sends secret + newline
            secret_upd = _make_update("/secret my_sudo_pass", user_id=42)
            await by_name["cmd_secret"].callback(secret_upd, MagicMock())
            secret_upd.message.delete.assert_awaited_once()
            mock_shell.write.assert_called_with(b"my_sudo_pass\n")

            # /ctrlc sends \x03
            ctrlc_upd = _make_update("/ctrlc", user_id=42)
            await by_name["cmd_ctrlc"].callback(ctrlc_upd, MagicMock())
            mock_shell.write.assert_called_with(b"\x03")

    asyncio.run(_run())
