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
6. **Turso Network Resilience & Retry**: Kueri remote database melalui `AiosqliteConnectionMock` dilengkapi mekanisme *auto-retry* 3x dengan backoff dan re-inisialisasi client jika koneksi TCP *keep-alive* diputus oleh proxy/server saat idle.
7. **Isolasi Middleware Group -1**: Eksekusi background `global_profile_tracker` dilindungi blok `try...except` agar kegagalan sinkronisasi metadata tidak menghentikan rantai pemrosesan update/perintah Telegram pengguna.
8. **Global Application Error Handler**: `Application` mendaftarkan `add_error_handler` terpusat di `main.py` untuk memastikan seluruh exception yang lolos tercatat secara komprehensif.
9. **Dual-Tier Promo Verification & Race-Condition Safe Locking**: Sistem validasi `/lpm` dan `/story` memverifikasi link promosi publik secara langsung melalui HTTP embed scraper (`verify_lpm_link_embed`) di bot utama serta background job queue (`process_promo_queue`) dan `checker.py`. Sistem menerapkan URL Canonicalization (`normalize_telegram_post_link`) untuk mencegah bypass duplikasi akibat variasi format (misal: query param `?single`, huruf besar/kecil, atau trailing slash). Status transisi atomik (`PROCESSING`) dan pengecekan konkurensi memastikan background queue maupun foreground command tidak saling tumpang tindih (*race condition*) dalam memvalidasi atau memberikan reward poin Agra ganda (*double claim*).
10. **Periodic Attendance Auto-Close Job**: Job queue menjalankan `periodic_auto_close_attendance` secara berulang (interval 60 detik) untuk menutup sesi presensi manual yang telah berumur $\ge$ 2 jam (`opened_at + 7200`) secara otomatis di database Turso, mencegah sesi menggantung atau memblokir pembukaan sesi baru untuk kelas yang bersangkutan.
11. **Purva SKS Banking & Academic Pruning**: Saat seorang mahasiswa bertransisi menjadi alumni (`purva`), sistem membersihkan atribut perkuliahan aktif (`major`, `class_enrolled`, `club_enrolled`, `student_id`) dari profil aktif sekaligus membekukan dan mengalihkan perolehan SKS perkuliahan lama ke dalam saldo `accumulated_sks`. Auto-enrollment kelas umum (`_apply_generated_profile_fields`) dibatasi ketat hanya untuk peran aktif (`student` dan `bem`), menjaga integritas data riwayat akademik alumni.
12. **Modular Import Isolation & Shadowing Prevention**: Seluruh impor modul pihak ketiga dan utilitas sistem (`telegram`, `html`, `logging`, `time`, `.common`) distandarisasi di tingkat modul (file header). Hal ini mencegah runtime `UnboundLocalError` laten akibat name binding shadowing dalam cakupan fungsi asynchronous Python.
13. **Contract Lifecycle State Machine & H-7 Rollover**: Sistem manajemen kontrak kerja (`kontrak.py`) memisahkan aset tanda tangan (`ttd_file_id`) dari eksekusi penerbitan kontrak resmi. Staf lama yang memperbarui tanda tangan saat kontrak aktif tidak memicu penerbitan ulang masa kontrak maupun spam notifikasi owner. Pada masa transisi H-7 sebelum penutupan periode (tanggal $\ge$ 10 di bulan genap), pengesahan kontrak baru atau perpanjangan (`/kontrak renew`) secara otomatis dialihkan ke tanggal 17 bulan genap berikutnya (+2 bulan). Seluruh riwayat kontrak disimpan dalam log teks terstruktur (`contract_history`) tanpa memerlukan redundansi penyimpanan gambar masa lalu.
