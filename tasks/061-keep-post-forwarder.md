# Fitur Auto Forward KEEP ke POST

## Deskripsi Task
Membuat fitur baru untuk mem-forward seluruh pesan dari channel KEEP ke channel POST secara otomatis setiap hari pada pukul 15:00 WIB. Mengingat batas rate limit Telegram, forwarding dipecah ke dalam batch (kelompok) maksimal 100 post, dengan jeda antar kelompok.

## Solusi Teknis (Menggunakan Pyrogram)
- Memanfaatkan kredensial `API_ID` dan `API_HASH` yang sudah ada di environment variables untuk menginisialisasi Pyrogram `Client` secara *in-memory* menggunakan token bot.
- Pyrogram dijalankan setiap pukul 15:00 WIB melalui `JobQueue` dari python-telegram-bot (`daily_keep_to_post`).
- **Forwarding:** Pyrogram otomatis melakukan chunking jika ID pesan melebihi 100. Seluruh ID langsung dilempar ke `app.forward_messages` secara bersamaan tanpa sistem *sleep* manual karena beban di bawah 300 pesan.
- **Pembersihan Otomatis:** Bot tidak melakukan operasi penghapusan apa pun dan tidak menggunakan database. Duplikasi dihindari secara murni memanfaatkan fitur bawaan Telegram (Auto-Delete TTL 24 jam) di channel KEEP.

## File yang Diubah
1. `bot/settings.py` - Menambahkan variabel `API_ID` dan `API_HASH` untuk dibaca dari `.env`, serta menambahkan `KEEP_CH_ID` dan `POST_CH_ID`.
2. `bot/jobs.py` - Menambahkan fungsi `daily_keep_to_post` menggunakan integrasi instan Pyrogram, dan mendaftarkannya pada jadwal `run_daily` di pukul 15:00 WIB.
