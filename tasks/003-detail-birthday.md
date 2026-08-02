# Fitur /detail dan Pengingat Ulang Tahun H-3

## Konteks & Permintaan
User menginginkan fungsionalitas di mana data tanggal lahir dapat diakses lebih cepat, terurut, dan dilengkapi pengingat otomatis, terutama untuk keperluan redaksi/editor (mengucapkan ulang tahun kepada anggota fakultas).
1. Perintah `/detail` yang meniru gaya `/daftar`, namun disortir berdasarkan waktu terdekat dari hari ini menuju ulang tahun pengguna, dan menelurkan baris format kustom berisi Tanggal Lahir dan Muse.
2. Fitur `daily_birthday_reminder` yang dipanggil setiap pukul 08:00 WIB untuk memberitahukan tim di grup `EDITOR_GID` bila ada anggota yang akan ulang tahun dalam 3 hari ke depan.

## Solusi Implementasi
1. **Datetime Utilities (`bot/timefmt.py`)**:
   Membuat modul hitungan tanggal (date math) `days_until_next_birthday` yang mengekstrak nilai string `DDMMYY` menjadi format tanggal, dan menghitung selisih ke ultah selanjutnya pada tahun berjalan atau tahun berikutnya, menggunakan _timezone_ Asia/Jakarta.
2. **Commands Router (`bot/handlers/commands.py`)**:
   Menulis `cmd_detail` di bawah `cmd_daftar`. Memiliki kapabilitas _filter_ yang sama, lalu setiap baris hasil disimpan ke memori untuk disortir `.sort(key=lambda x: x["dist"])`. Hasil diformat menjadi 2 baris (Nama - Tanggal Lahir & Muse).
3. **Pendaftaran Command (`bot/handlers/register.py`)**:
   Dimasukkan secara mulus ke dalam siklus pemuatan aplikasi.
4. **Cron Job Pengingat (`bot/jobs.py` & `.env` & `settings.py`)**:
   Mengikat _job_ baru ke siklus `job_queue.run_daily` di waktu `08:00 WIB`. Sistem akan mendeteksi `EDITOR_GID` dan mengirimkan kompilasi nama-nama yang akan berulang tahun persis H-3.

## Temuan QA & Perbaikan (Hotfix)
Pasca-implementasi, proses *Quality Assurance* menemukan celah kerentanan berikut yang telah ditutup (*patched*):
- **Leapling Bug**: Penghitungan waktu untuk pengguna kelahiran 29 Februari akan *error* di tahun non-kabisat. Diperbaiki dengan menggeser peringatan ke 1 Maret pada tahun biasa.
- **HTML Injection (XSS)**: Fitur `/daftar`, `/detail`, dan pengingat grup mem- _parsing_ respons ke mode HTML. Celah XSS terjadi jika anggota meretas namanya atau isian _muse_ menjadi tag HTML (mis: `<script>`), yang akan membuat format bot rusak dan menolak mengirim (_crash_). Ditambal penuh dengan integrasi `html.escape`.
- **Privilege Escalation (Scope Bypass)**: Fitur `/detail` pada awalnya melupakan filter `dean_mode` dan `lec_mode` dari bot utama. Menyebabkan Dekan / Dosen yang menggunakan `/detail` bisa melihat daftar ulang tahun mahasiswa di luar jangkauan (seluruh fakultas!). Celah isolasi data ini sekarang tertutup dengan algoritma `user_in_dean_faculty_scope`.

Semua pekerjaan telah selesai dieksekusi.
