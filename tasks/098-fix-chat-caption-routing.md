# Task 098: Perbaikan Handler Routing `/chat` pada Media Caption

## Deskripsi Singkat
Memperbaiki bug di mana pengiriman pesan `/chat` yang dilampirkan langsung sebagai **caption** pada media (foto, video, dokumen, audio, dll.) tidak terkirim ke penerima target karena keterbatasan internal `CommandHandler` pada `python-telegram-bot` (PTB).

## Masalah & Analisis Akar Masalah (Root Cause)
1. **Keterbatasan PTB `CommandHandler`**:
   - Fungsi `CommandHandler("chat", commands.cmd_chat)` hanya memproses pesan teks murni (`update.message.text` dan `update.message.entities`).
   - Pada pesan media (seperti foto dengan caption), atribut `update.message.text` bernilai `None`, dan entitas tersimpan di `update.message.caption_entities`.
   - Akibatnya, `CommandHandler` mengabaikan seluruh pesan media yang menggunakan caption `/chat @username [pesan]`, sehingga `cmd_chat` sama sekali tidak pernah terpanggil dan pesan tidak terkirim ke target penerima.
2. **Fallback ke Handler Private Message**:
   - Karena filter `~filters.COMMAND` juga hanya memeriksa entitas teks murni, pesan foto dengan caption `/chat` jatuh ke `on_private_message` (Group 1).
   - Di sana, pesan tersebut dianggap sebagai pesan biasa dan berpotensi diteruskan ke grup log Petinggi alih-alih dieksekusi sebagai perintah.

## Perubahan yang Dilakukan
1. **Penyatuan Handler Menjadi Single MessageHandler (`bot/handlers/register.py`)**:
   - Menggabungkan penanganan teks dan caption ke dalam 1 handler tunggal menggunakan operator OR (`|`):
     `filters.Regex(re.compile(r"^/chat(?:@\w+)?(?:\s|$)", re.IGNORECASE)) | filters.CaptionRegex(re.compile(r"^/chat(?:@\w+)?(?:\s|$)", re.IGNORECASE))`
   - Menghilangkan duplikasi registrasi handler di `register.py` sehingga kodenya ringkas dan efisien.
2. **Pencegahan Forward /chat ke Grup Petinggi (`bot/handlers/messages.py`)**:
   - Pada `on_private_message`, menambahkan pengecekan spesifik `if text.lower().startswith("/chat"): return` saat pengguna tidak dalam status onboarding (`not step`).
   - Khusus mencegah perintah `/chat` milik owner bocor ke grup `PETINGGI_GID`, tanpa memblokir pesan atau caption pengguna umum lainnya.
3. **Penambahan Unit Test (`tests/test_chat_command.py`)**:
   - Menambahkan pengujian kasus pengiriman foto langsung dengan caption `/chat @charlie Ini foto tugas!` (memverifikasi bahwa `message.copy` dipanggil dengan `caption="Ini foto tugas!"`).
   - Menambahkan pengujian kasus pengiriman foto dengan caption `/chat @charlie` tanpa teks tambahan (memverifikasi bahwa caption di-strip dan dikirim polos dengan `caption=""`).
   - Memperbaiki `send_message_or_media_to_target` di `bot/handlers/common.py` agar meneruskan `caption=""` (string kosong) alih-alih `None` ketika pesan media dikirim tanpa teks ekstra, karena Telegram API `copyMessage` secara default mempertahankan caption asli jika parameter caption bernilai `None`/tidak dispesifikasikan.
   - Seluruh pengujian pada `tests/test_chat_command.py` lulus 100%.
