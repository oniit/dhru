# Task 139: Penerapan Perbaikan Celah QA, Optimasi Turso, dan Integrasi Help Kelulusan

## Ringkasan Eksekutif
Menuntaskan seluruh perbaikan (*hardening*) dari hasil QA Audit pada sistem Ijazah & Transkrip Shishya (`bot/graduation_excel.py`, `bot/transkrip_card.py`, `bot/ijazah_card.py`, `bot/handlers/graduation.py`), menambahkan index database Turso untuk perlindungan kuota pembacaan baris (*rows read*), mengintegrasikan menu perintah kelulusan ke `/help`, serta memverifikasi kesiapan operasional bot dengan token Telegram baru.

---

## Rincian Perbaikan & Penyesuaian

### 1. Hardening Keamanan & Logika Bisnis Kelulusan
- **Pemberantasan Celah IDOR**: Menghapus pencocokan substring liar berbasis `first_name` Telegram pada `_find_student()`. Menolak akses akun berstatus `ROLE_PUBLIC`. Self-service hanya dapat diakses melalui NIM resmi (`student_id`) yang terverifikasi di profil akun.
- **Isolasi Pasfoto Admin vs Mahasiswa**: Memperbaiki `_get_photo_bytes_for_student()` sehingga saat Admin melakukan lookup mahasiswa lain (misal: `/transkrip 2004010093`), bot mencari data mahasiswa di database Turso. Jika pasfoto KTS kosong, bot melakukan *fallback* ke pasfoto Telegram shishya bersangkutan (`target_uid`), bukan menempelkan foto profil Admin.
- **Ketahanan Event Loop Async**: Memindahkan eksekusi batch export 42 dokumen PNG dan pembuatan ZIP ke thread latar belakang (`asyncio.to_thread(_sync_export_documents)`) sehingga bot tidak mengalami freeze.
- **In-Memory Cache & Penghapusan `optimize=True`**: Mengurangi waktu render dari 1.050 ms ke ~310 ms per gambar, dan 0 ms untuk cache hit.
- **Resilience Windows File Lock**: Menangani `PermissionError` saat `Template IPK.xlsx` dibuka di Microsoft Excel dengan menyalinnya ke temporary file.
- **Kelengkapan Pemetaan Gelar**: Memperkaya alias jurusan pendek (`kimia`, `fisika`, `musik`) pada `DEGREE_MAP`.

### 2. Optimasi Database Turso (Perlindungan Kuota)
- Menambahkan index fungsional baru:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_users_student_id ON users(json_extract(profile_json, '$.student_id'));
  ```
  Hal ini mencegah *Full Table Scan* pada tabel `users` saat pencarian foto atau data shishya berdasarkan NIM.

### 3. Integrasi Menu Bantuan (`/help`)
- Menambahkan perintah `/transkrip` dan `/ijazah` pada teks `/help` untuk peran Shishya (`student`), BEM, dan Alumni (`purna`).
- Menambahkan perintah `/export_kelulusan [zip]`, `/transkrip [nim]`, dan `/ijazah [nim]` pada teks `/help` untuk peran Admin dan Owner.

### 4. Sanitasi Konfigurasi & Verifikasi Bot Token
- Memperbaiki parsing `BOT_TOKEN` di `bot/settings.py` agar secara eksplisit membersihkan komentar inline (`#...`).
- Berhasil memverifikasi koneksi API Telegram dengan token baru (`@dhrvabot`, ID 9269210473).

---

## Verifikasi
- Pengujian parser Excel, generator transkrip, generator ijazah, dan batch export berjalan sukses tanpa error.
- Semua 30 mahasiswa dapat diproses dengan layout presisi tanpa overflow.
- Bot siap dijalankan di terminal secara live.

