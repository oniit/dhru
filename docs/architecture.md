# System Architecture

## Gambaran Umum
Sistem bot ini dibangun di atas bahasa Python menggunakan **`python-telegram-bot` (versi 20+)** dengan pendekatan asynchronous murni (`asyncio`). Sistem menggunakan **Turso** (remote database via `libsql_client`) sebagai basis datanya.

## Tech Stack
- **Bahasa**: Python 3.10+
- **Framework Bot**: `python-telegram-bot` (v20+)
- **Database**: Turso DB (`libsql_client` / `aiosqlite`)
- **Konfigurasi**: YAML (untuk data master/choices) dan `.env` (untuk _credentials_ `TURSO_DB_URL` & `TURSO_AUTH_TOKEN`).

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
    ├── kic.py     # Generator ID Card Pegawai.
    ├── kontrak.py    # Pembuatan dan manajemen kontrak.
    ├── kts.py        # Generator Kartu Tanda Shisya (KTS).
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

## Proteksi Keamanan & Integritas State
1. **IDOR & Scope Guard**: Modul tugas (`tugas.py`) memvalidasi kepemilikan kelas (`_student_enrolled_class_ids`) baik pada interaksi callback inline (`tsi:`) maupun pengumpulan jawaban (`handle_tugas_input`) untuk mencegah mahasiswa mengakses tugas di luar fakultas/jurusannya.
2. **Anti Self-Approval**: Pada workflow persetujuan profil (`commands.py`), reviewer tidak diperkenankan menyetujui (`a:<id>:1`) atau menolak pengajuannya sendiri, kecuali dengan role `owner`.
3. **Atomic Sequence Generator**: Penomoran dokumen dinamis seperti surat kontrak kerja staf dihitung menggunakan generator atomic (`get_next_contract_seq`) pada tabel `bot_settings`, mencegah *race condition* dan duplikasi nomor urut pada eksekusi serentak.
4. **Proteksi Finansial & State Menfess**: Transaksi debit saldo Agra pada menfess (`menfess.py`) selalu memvalidasi kelengkapan data sesi (`target_id`, `message_text`) sebelum pemotongan saldo, serta menjamin *auto-refund* jika pengiriman pesan ke channel gagal.
5. **Sanitasi HTML Parsing**: Semua parameter dinamis pengguna (`first_name`, `username`, `reason`, dll) disanitasi menggunakan `html.escape` sebelum diinterpolasi ke format HTML Telegram guna mencegah `Bad Request: Can't parse entities`.
