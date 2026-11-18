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
    ├── pfp.py        # Forward postingan channel ke KEEP channel & rekap statistik Owner.
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
11. **Purna SKS Banking & Academic Identity Retention**: Saat seorang mahasiswa bertransisi menjadi alumni (`purna`), sistem membersihkan atribut perkuliahan semester aktif (`class_enrolled`, `club_enrolled`) dari profil aktif sekaligus membekukan dan mengalihkan perolehan SKS perkuliahan lama ke dalam saldo `accumulated_sks`. Nomor Induk Mahasiswa (`student_id` / NIM) sengaja dipertahankan secara permanen pada profil alumni agar mereka dapat mengakses dokumen kelulusan mandiri (`/transkrip` dan `/ijazah`) kapan saja dengan validasi identitas resmi tanpa bergantung pada kesamaan nama profil Telegram. Auto-enrollment kelas umum (`_apply_generated_profile_fields`) dibatasi ketat hanya untuk peran aktif (`student` dan `bem`).
12. **Modular Import Isolation & Shadowing Prevention**: Seluruh impor modul pihak ketiga dan utilitas sistem (`telegram`, `html`, `logging`, `time`, `.common`) distandarisasi di tingkat modul (file header). Hal ini mencegah runtime `UnboundLocalError` laten akibat name binding shadowing dalam cakupan fungsi asynchronous Python.
13. **Contract Lifecycle State Machine & H-7 Rollover**: Sistem manajemen kontrak kerja (`kontrak.py`) memisahkan aset tanda tangan (`ttd_file_id`) dari eksekusi penerbitan kontrak resmi. Staf lama yang memperbarui tanda tangan saat kontrak aktif tidak memicu penerbitan ulang masa kontrak maupun spam notifikasi owner. Pada masa transisi H-7 sebelum penutupan periode (tanggal $\ge$ 10 di bulan genap), pengesahan kontrak baru atau perpanjangan (`/kontrak renew`) secara otomatis dialihkan ke tanggal 17 bulan genap berikutnya (+2 bulan). Seluruh riwayat kontrak disimpan dalam log teks terstruktur (`contract_history`) tanpa memerlukan redundansi penyimpanan gambar masa lalu.
14. **Chāryārthī Division Quiz & SDM Channel Streaming**: Alur pendaftaran staf (`charyarthi`) menyajikan dashboard tes esai dinamis per divisi pilihan. Seluruh lembar jawaban dan alasan mendaftar dilindungi mekanisme anti-limit Telegram (4.096 karakter):
    - **Pratinjau Paginated**: Jika total teks pratinjau melebihi 3.500 karakter, sistem otomatis mengalihkan tampilan ke mode per nomor soal (`charyarthi:prev_q`) dengan navigasi interaktif.
    - **Answer Chunking**: Jawaban esai berukuran panjang dipecah secara rekursif menjadi sub-bagian $\le$ 2.400 karakter dan dipaketkan ke dalam blok pesan bertahap $\le$ 3.400 karakter, dikirimkan secara langsung ke channel khusus Tim SDM (`SDM_CH_ID`).
    - **Answer Sanitization on Reset & Rejection**: Jawaban tes (`charyarthi_answers`) dan atribut pendaftaran otomatis dibersihkan saat user membatalkan pendaftaran (`cancel`), ditolak oleh admin (`reject_charyarthi`), atau di-reset melalui perintah `/orreset_user` dan fungsi reset operasional database.
    - **Privacy Kata Kunci Promosi**: Pesan penolakan validasi LPM tidak lagi membocorkan kata kunci internal (`promo_lpm_keyword`) kepada pengguna demi mencegah eksploitasi.
15. **Graduation & Academic Transcript Pipeline**: Sistem kelulusan (`graduation.py`, `graduation_excel.py`, `transkrip_card.py`, `ijazah_card.py`) mengintegrasikan parsing spreadsheet kelulusan (`Template IPK.xlsx`) dan rendering grafis dokumen resmi menggunakan modul Pillow dengan tipografi Open Serif (untuk teks transkrip dan isi ijazah) serta Cinzel Bold (khusus nama di ijazah). Sistem memisahkan IPK Akademik murni (4 Matkul wajib) dengan Indeks Keaktifan Kumulatif (IKK dari UKM), memvalidasi batas kelulusan (IPK > 2.00), serta mendukung distribusi dokumen secara mandiri via PM bot (`/transkrip`, `/ijazah`) maupun ekspor massal terpusat (`/export_kelulusan zip`) oleh admin. Pipeline ini dilengkapi proteksi IDOR ketat (klaim mandiri hanya melalui NIM/nama lengkap resmi, bukan display name Telegram), isolasi pasfoto target pada pencarian admin, penanganan Windows file lock pada Excel, serta isolasi background thread worker guna mencegah pemblokiran event loop asyncio.
    - **Dual-Layer Auto-Archive & Turso Mirroring**: Sistem mengadopsi mekanisme arsip kumulatif berbasis JSON lokal (`data/graduation_records.json`) sebagai sumber pembacaan primer berprioritas tertinggi dengan *in-memory caching* instan (0 *rows read* ke Turso). Setiap generasi baru, pengelola dapat mengganti/menimpa isi `Template IPK.xlsx` hanya dengan data angkatan berjalan tanpa perlu menyimpan baris angkatan lama; sistem otomatis me-*merge* data baru ke arsip JSON tanpa menghapus arsip generasi sebelumnya. Data kelulusan juga di-mirror secara otomatis ke tabel remote `graduation_records` Turso sebagai redundansi cadangan cloud terpusat.
    - **Dynamic Generation Packaging & ZIP Data Preservation**: Folder keluaran (`output/kelulusan_gen{N}/`) dan paket arsip ZIP (`Dokumen_Kelulusan_Gen{N}.zip`) kini dinamik mengikuti variabel `GENERATION_CODE` dari environment. Sistem secara otomatis menyertakan berkas data JSON (`graduation_records_gen{N}.json`) baik di folder keluaran maupun di dalam paket ZIP keluaran, sehingga siapa pun yang mengekstrak berkas dapat memverifikasi sumber data mentah transkrip dan ijazah angkatan tersebut. Didukung pintasan perintah `/sync_kelulusan` atau `/export_kelulusan sync` untuk sinkronisasi kilat tanpa merender gambar.
16. **Mass Generation Rollover & Tutup Generasi (`setrole purna all`)**: Saat generasi akademik berakhir, pengelola tidak perlu mengubah peran mahasiswa satu per satu via `@mention`. Sistem menyediakan eksekusi massal aman:
    - **Sintaks Massal Fleksibel**: Perintah `/setrole purna <all|shishya|bem|massal|semua>` dan `/tutup_generasi [konfirmasi]` mengeksekusi migrasi peran massal seluruh mahasiswa aktif (`student` dan/atau `bem`) secara otomatis.
    - **Proteksi Eskalasi Ketat**: Eksekusi massal dibatasi keras (`is_mass` validation) hanya untuk target role `ROLE_PURNA` dan hanya dapat dipanggil oleh Owner. Upaya eksekusi massal pada role lain (misal: `/setrole admin all`) secara instan ditolak dengan peringatan keamanan.
    - **Integritas Akademik & Audit Otomatis**: Setiap mahasiswa yang diluluskan secara otomatis dibukukan total SKS-nya ke `accumulated_sks`, NIM (`student_id`) dipertahankan untuk self-service `/transkrip` dan `/ijazah`, mata kuliah serta UKM aktif dibersihkan, notifikasi privat kelulusan dikirim bertahap (*throttled* untuk mencegah *FloodWait* Telegram), dan setiap tindakan tercatat dalam tabel `audit_log` (`mass_set_role_purna`).
    - **Optimalisasi Indeks Turso**: Kolom `users.role` dilindungi indeks DDL permanen (`CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)`) guna mencegah *Full Table Scan* dan menghemat kuota *rows read* Turso saat kueri penyaringan kandidat mahasiswa aktif dijalankan.
