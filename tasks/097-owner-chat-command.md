# Task 097: Fitur /chat Owner & Penyatuan Logika Pengiriman Polos dengan #balas

## Deskripsi Singkat
Menambahkan fitur perintah baru `/chat <@username|ID> <pesan>` khusus untuk Owner agar dapat mengirimkan pesan langsung ke private chat (PM) pengguna atas nama bot secara polos (tanpa watermark/header). Fitur ini mendukung pengiriman teks, lampiran media langsung (foto/video/dokumen/audio/voice/stiker/video note), maupun dengan me-reply media apa pun. Logika pengiriman dan resolusi pengguna disatukan ke dalam fungsi helper bersama sehingga perintah `#balas` juga mewarisi kemampuan resolusi target eksplisit.

## Detail Pekerjaan
1. **Helper Pengiriman Bersama (`bot/handlers/common.py`):**
   - Membuat fungsi `send_message_or_media_to_target(bot, target_id, message, text_or_caption="", source_message=None)`:
     - Mengirim teks murni menggunakan `bot.send_message(..., parse_mode=None)` secara polos.
     - Menyalin media (foto, video, dokumen, audio, voice, animation) menggunakan `copy()`, menjaga caption asli atau menimpanya dengan teks baru.
     - Mengirim stiker atau video note menggunakan `copy()`, dan jika disertai teks balasan, mengirimkannya sebagai pesan teks terpisah.
     - Mendukung parameter `source_message` saat owner me-reply pesan/media lain.
2. **Helper Resolusi Pengguna Multilevel (`bot/handlers/common.py`):**
   - Membuat fungsi `resolve_target_user(conn, db, target_arg)`:
     - Level 1: Menguji apakah argumen berupa numeric Telegram ID langsung.
     - Level 2: Mencari username di tabel `users`.
     - Level 3: Mencari username di tabel `group_seen_users`.
     - Level 4: Fallback sekunder menggunakan IPC Userbot (`userbot_requests` dengan action `RESOLVE:<username>`) jika user asing belum tersimpan di database lokal.
3. **Handler Perintah `/chat` (`bot/handlers/commands.py`):**
   - Menambahkan fungsi `cmd_chat`:
     - Otorisasi ketat khusus Owner via `is_owner(uid)`.
     - Parsing fleksibel mendukung teks dan caption media langsung.
     - Penanganan error komprehensif untuk `Forbidden` (bot diblokir) dan `BadRequest` (user belum pernah `/start` bot).
4. **Penyatuan dengan `#balas` (`bot/handlers/messages.py`):**
   - Memodifikasi blok penanganan `#balas`:
     - Jika me-reply pesan bot yang memiliki hashtag `#ID_<user_id>`, tetap menggunakan ID tersebut (backward-compatible).
     - Jika tidak me-reply tiket bot atau admin mengetik `#balas @username <pesan>`, bot otomatis me-resolve target menggunakan `resolve_target_user`.
     - Menyerahkan eksekusi pengiriman ke `send_message_or_media_to_target`.
5. **Registrasi Handler (`bot/handlers/register.py`):**
   - Mendaftarkan `CommandHandler("chat", commands.cmd_chat)`.
6. **Dokumentasi (`docs/commands.md`):**
   - Mendokumentasikan perintah `/chat` pada bagian Manajemen.

## Status QA
- [x] Syntax & import check pass.
- [x] Tested: `resolve_target_user` berhasil me-resolve ID numerik, username tabel `users`, dan `group_seen_users`.
- [x] Tested: `send_message_or_media_to_target` berhasil mengirim teks, foto langsung, reply foto dengan caption override, dan mempertahankan caption asli.
- [x] Tested: `cmd_chat` memblokir non-owner, memvalidasi argumen kosong, mengirim pesan ke target yang valid, dan menangani error `chat not found`.
- [x] Tested: `test_logic.py` regression test pass.
