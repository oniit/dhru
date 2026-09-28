# 085 - Fix Sinkronisasi Presensi Sachiva (d_sekre)

## Latar Belakang
User melaporkan bahwa setelah update sebelumnya (terkait penambahan izin buka sesi presensi untuk Sachiva / `d_sekre`), mereka malah mendapatkan error *"Sesi ini di luar akses presensi kamu"* atau peringatan *"Hanya untuk staf"* ketika mencoba untuk **mengisi/hadir** pada sesi presensi tersebut (baik untuk `staff_manual` maupun `staff_auto`).

## Penyebab (Root Cause)
Pada update [078](078-allow-sachiva-manual-staff-presensi.md), kita sudah berhasil mengizinkan Sachiva (`d_sekre`) untuk **membuka** sesi `staff_manual` dan `staff_auto` melalui fungsi `presence_allowed_class_ids()` di `bot/handlers/common.py`. 
Namun, akses untuk **menghadiri/mengisi presensi** yang diatur dalam variabel list `user_classes` (yang ada di dalam `bot/handlers/attendance.py`) ternyata tidak ikut di-update secara sinkron. Fungsi pengecekan di sana hanya mengecek apakah role user adalah `ROLE_INTERNAL`, `ROLE_ADMIN`, atau `ROLE_OWNER` saja. Jika Sachiva kebetulan memiliki *role Telegram* di luar itu (misal `ROLE_BEM` atau `ROLE_STUDENT`), mereka akan ditolak.

## Perbaikan yang Dilakukan
Di `bot/handlers/attendance.py`, kami mengimpor fungsi `get_user_jabatans` dan mengekstrak `jabs` dari `profile`. Kami menyisipkan validasi pengecekan tambahan:
1. **Di dalam `cmd_hadir`**: Kami menambahkan kondisi `or "d_sekre" in jabs` agar `staff_manual` di-append ke daftar kelas valid milik Sachiva.
2. **Di dalam `cb_attendance_action`**: 
   - Untuk tombol `sh` (`staff_auto`), kami merilekskan blokiran `if row["role"] not in ...` menjadi `and "d_sekre" not in jabs`.
   - Untuk validasi fallback di luar tombol `sh` (seperti saat klik opsi "Hadir" pada `staff_manual`), kami juga menambahkan pengecekan `or "d_sekre" in jabs` saat meng-append `staff_manual` ke list kelas milik user. 

Hal ini memastikan sinkronisasi antara hak akses *"Buka Presensi"* dan hak akses *"Isi Presensi"* untuk jabatan spesifik Sachiva.
