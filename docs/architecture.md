# System Architecture

## Gambaran Umum
Sistem bot ini dibangun di atas bahasa Python menggunakan **`python-telegram-bot` (versi 20+)** dengan pendekatan asynchronous murni (`asyncio`). Sistem menggunakan **SQLite** (melalui library `aiosqlite`) sebagai basis datanya, memastikan performa tinggi dengan sumber daya server yang sangat ringan.

## Tech Stack
- **Bahasa**: Python 3.10+
- **Framework Bot**: `python-telegram-bot` (v20+)
- **Database**: SQLite3 (`aiosqlite`)
- **Konfigurasi**: YAML (untuk data master/choices) dan `.env` (untuk _credentials_).

## Struktur Direktori

```text
bot/
├── database.py       # Kelas inti yang membungkus semua interaksi dan query SQLite.
├── settings.py       # Pemuat konfigurasi (.env, YAML) dan konstanta sistem.
├── timefmt.py        # Utilitas format zona waktu lokal.
└── handlers/         # Kumpulan modul logika (router) berdasarkan fitur.
    ├── attendance.py # Logika presensi (buka sesi, hadir, rekap).
    ├── broadcast.py  # Fitur pengiriman pesan massal.
    ├── commands.py   # Perintah inti (/start, /profil, /admin_data, /owner_reset).
    ├── common.py     # Fungsi utilitas (role checking, keyboard builders).
    ├── karpeg.py     # Generator ID Card Pegawai.
    ├── kontrak.py    # Pembuatan dan manajemen kontrak.
    ├── ktm.py        # Generator Kartu Tanda Mahasiswa (KTM).
    ├── messages.py   # Tracker grup, pemantau username, penangkap teks fallback.
    ├── triggers.py   # Logika auto-reply kustom.
    └── tugas.py      # Pengumpulan dan review tugas.
```

## Alur Kerja Pesan (_Message Flow_)
1. Pengguna mengirim pesan ke bot.
2. `Application` (_router_ PTB) menerima _Update_.
3. Pemrosesan Group -1 (Middleware):
   - `global_profile_tracker` di `messages.py` mencegat _Update_ untuk memeriksa apakah nama pengguna/username berubah, jika ya, perbarui _cache_ dan DB.
4. Pemrosesan Group Utama (0, 1, 2):
   - Diteruskan ke handler yang sesuai (misal `CommandHandler` atau `MessageHandler`).
   - Handler memanggil koneksi `aiosqlite` melalui `context.bot_data["conn"]`.
   - Handler mengirimkan tanggapan via `update.message.reply_text`.
