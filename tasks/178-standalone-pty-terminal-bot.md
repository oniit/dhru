# Task 178: Standalone 2-Way Full PTY Terminal Bot (`terminal_bot.py`)

## Latar Belakang
User menginginkan satu file Python statis yang berjalan terpisah dari bot utama (`main.py`) untuk menjembatani Telegram private chat dengan terminal VPS secara 2 arah (kirim perintah maupun balas prompt interaktif dan terima output terminal langsung di Telegram).

## Implementasi Teknis
- **`terminal_bot.py`** (file tunggal mandiri di root proyek, tanpa ketergantungan ke modul `bot/` ataupun database Turso):
  1. **Konfigurasi & Keamanan (`TerminalConfig`, `is_authorized`)**:
     - Memuat `.env` (via `python-dotenv` atau parser fallback bawaan).
     - Membaca `TERMINAL_BOT_TOKEN` (wajib) dan whitelist ID pemilik dari `TERMINAL_OWNER_IDS` dengan fallback ke `OWNER_ID` (wajib).
     - Menolak semua interaksi selain dari `chat.type == "private"` dan ID pemilik numerik terdaftar.
  2. **Engine Full PTY (`PtyShell`)**:
     - Membuka pasangan pseudo-terminal (`pty.openpty()`) pada OS Linux/POSIX dan menjalankan shell (`TERMINAL_SHELL`, default `$SHELL` / `/bin/bash`) dengan `os.setsid()` dan `TIOCSCTTY` agar kontrol job dan sinyal `Ctrl+C` (`SIGINT`) berjalan normal serta terisolasi dari proses `terminal_bot.py`.
     - Memantau `master_fd` secara non-blocking menggunakan `loop.add_reader(...)` tanpa busy-polling loop.
     - Mendukung `resize(cols, rows)` (`TIOCSWINSZ`) dan shutdown bersih (`SIGTERM` -> `SIGKILL` process group).
  3. **Sanitasi & Buffer Layar (`TerminalBuffer`)**:
     - Menangani escape sequence ANSI/OSC/CSI yang terpotong lintas chunk pembacaan (`_esc_buf`), menghapus judul window (`OSC`), kode warna (`CSI`), menghapus baris (`\x1b[K`, `\x1b[2K`), membersihkan layar (`\x1b[2J`), serta mensimulasikan `\r`, `\b`, dan `\t` sehingga progress bar di-update rapi di tempat.
  4. **Streaming 2 Arah (`TerminalBridge`)**:
     - Melakukan debounce (`0.65s`) saat streaming output agar aman dari `FloodWait` (beserta handler retry otomatis `RetryAfter`).
     - Memisahkan pesan aktif setiap kali user mengirim input baru (`detach_message=True`), sehingga balasan terminal selalu muncul sebagai pesan baru di bawah input user.
     - Memecah output panjang secara aman berdasarkan panjang setelah `html.escape` (`MAX_PRE_HTML_CHARS = 3800`) dan mengirim output sangat besar (`> 15000` char escaped) sebagai file `terminal_output.txt` ditambah cuplikan baris terakhir.
     - Melindungi notifikasi exit shell dengan penanda generasi sesi (`_session_gen`) agar race condition setelah `/reset` tidak menghapus sesi baru.
     - Menyediakan perintah kontrol (`/ctrlc`, `/ctrld`, `/ctrlz`, `/enter`, `/tab`, `/esc`, `/raw`, `/send`, `/secret`, `/resize`, `/status`, `/reset`) dan tombol inline pada output aktif.
- **`tests/test_terminal_bot.py`**: Pengujian unit offline untuk `TerminalBuffer`, `split_for_telegram_html`, `TerminalConfig` + `is_authorized`, `TerminalBridge` (streaming, detach, file fallback, exit guard), serta routing handler aplikasi.
- **`docs/architecture.md` & `docs/commands.md`**: Pembaruan dokumentasi arsitektur dan daftar perintah.

## Verifikasi
- `python -m pytest tests/test_terminal_bot.py -v`: **6 passed**.
