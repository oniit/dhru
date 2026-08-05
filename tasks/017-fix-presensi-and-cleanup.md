# Dokumentasi: Perbaikan Modul Presensi Otomatis & Pembersihan Lingkungan

## Ringkasan Tugas
1. **Perbaikan *Silent Failure* pada Presensi Otomatis**: Mengatasi isu di mana presensi otomatis gagal mengirimkan pesan pengingat ke DM staf (Internal, Admin, Owner) apabila terjadi gangguan jaringan/Bad Gateway saat percobaan pertama ke Channel utama.
2. **Penyesuaian Penerima Presensi**: Mengubah query penerima presensi agar hanya mengirimkan DM ke *role* `internal`, membebaskan `owner` dan `admin` dari tagihan presensi harian.
3. **Integrasi _Maba Group Links_ di `/setrole`**: Menyinkronkan perintah set manual `/setrole maba` agar otomatis menghitung kuota kelompok dan mendistribusikan link grup kelompok kepada mahasiswa baru.
4. **Pembersihan _Workspace_**: Menghapus seluruh _script testing_ sementara dan _file_ migrasi yang sudah usang agar direktori _project_ kembali bersih.

## Detail Implementasi Teknis

### 1. Robustness Presensi Otomatis (`bot/jobs.py`)
- **Masalah:** Fungsi `daily_staff_attendance_open` sebelumnya menangkap _NetworkError_ (misal 502 Bad Gateway) saat gagal mengepos ke Channel presensi, tetapi langsung mengeksekusi `return`. Ini membatalkan *loop* iterasi DM kepada seluruh Staf sehingga jadwal presensi "mati total" hari itu.
- **Solusi:** 
  - Mencabut instruksi `return`.
  - Menerapkan blok iterasi _auto-retry_ maksimal 3 kali untuk menangani _Bad Gateway_ sementara dengan *delay* `asyncio.sleep(5)`.
  - Menjamin bahwa meskipun pengiriman *channel* berulang kali gagal, iterasi pengiriman DM ke setiap staf tetap dieksekusi.

### 2. Filter Role Presensi Harian (`bot/database.py`)
- **Penyesuaian:** Mengembalikan kueri `get_all_staff_ids` agar secara ketat memuat daftar ID pengguna yang memiliki `role = 'internal'` saja. Admin dan Owner dikecualikan.

### 3. Penugasan Kelompok Otomatis `/setrole maba` (`bot/handlers/commands.py`)
- **Masalah:** Menggunakan perintah `/setrole` tidak memberikan link grup kepada pengguna dengan status maba.
- **Solusi:** Menyuntikkan _logic_ penghitungan otomatis berbasis rasio modular 4 (`% 4 + 1`) ke dalam `cmd_setrole`. Menginjeksi *link* undangan secara dinamis langsung ke teks balasan agar Maba segera diarahkan ke kelompoknya tanpa menunggu _onboarding_ ulang.

### 4. Cleanup File (`Workspace`)
Telah dijalankan perintah terminal untuk menghapus berkas berikut:
- `test_daily.py`, `test_jq.py`, `test_jq_real.py`, `test_input_code.py`, `test_public_onboarding.py` (Script Scratch/Testing)
- `test_logic_88.sqlite3`, `test_logic_99.sqlite3` (Database dummy testing)
- `migrate_vps_to_turso.py`, `migrate_turso.py`, `clean_prod.py` (Script Migrasi)
- `agra_ledger.sqlite3` (Database lokal usang pasca Turso)

## Status
- **Selesai**: Seluruh bug fungsionalitas logika telah diperbaiki dan dibersihkan.
