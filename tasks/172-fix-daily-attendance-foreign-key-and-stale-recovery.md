# Task 172: Perbaikan Presensi Harian (Foreign Key Constraint & Stale Session Recovery)

## 1. Masalah & Akar Penyebab (Root Cause Analysis)
1. **Kegagalan Foreign Key pada Eksekusi Cron Otomatis**:
   - Pada pembaruan sebelumnya (Task 156 / commit `ab9fa39` pada 16 November 2026), fungsi pembukaan presensi harian otomatis staf (`daily_staff_attendance_open` di `bot/jobs.py`) diubah agar menggunakan atribut `opened_by = 0` secara eksplisit ketika `opened_by is None`.
   - Skema tabel `attendance_sessions` di DDL database (`bot/database.py`) mendefinisikan kolom:
     `opened_by INTEGER NOT NULL, FOREIGN KEY (opened_by) REFERENCES users(telegram_id)`
   - Karena di tabel `users` tidak ada pengguna dengan `telegram_id = 0`, setiap kali cron job dieksekusi secara otomatis pada pukul 07:00 WIB, basis data remote Turso menolak operasi `INSERT INTO attendance_sessions` dengan error:
     `SQLite error: FOREIGN KEY constraint failed (SQLITE_CONSTRAINT)`
   - Akibat kegagalan tersebut, job terhenti tanpa mengirim pesan pembukaan presensi ke channel presensi (`PRESENCE_CH_ID`) maupun mengirim DM tombol hadir ke anggota staf. Masalah ini berlangsung sejak 17 November 2026 (sekitar seminggu terakhir) tepat setelah commit 16 November malam.
2. **Potensi Deadlock Sesi Basi (Stale Sessions)**:
   - Sebelum perbaikan, fungsi `daily_staff_attendance_open` dan `daily_maba_attendance_open` hanya memeriksa apakah ada sesi aktif (`get_open_session_for_class`). Jika ada, fungsi langsung keluar tanpa membuka sesi baru.
   - Jika bot sempat mati atau di-restart tepat pada pukul 23:59 WIB (saat jadwal `daily_staff_attendance_close`), sesi hari sebelumnya tidak pernah ditutup dan akan memblokir pembukaan sesi hari-hari berikutnya secara permanen.
3. **Blokir Presensi Mandiri Pembuka Sesi (Self-Attendance Guard)**:
   - Pada fungsi `_record_hadir` (`bot/handlers/attendance.py`), terdapat validasi:
     `if int(sess.get("opened_by") or 0) == uid and sess["class_id"] not in ("staff_manual", "bem_manual", "event_bebas"): return False, "Anda tidak perlu mengisi presensi untuk sesi yang Anda buka sendiri."`
   - Karena `staff_auto` dan `maba_auto` tidak dikecualikan, jika `opened_by` diisi dengan `OWNER_ID`, maka Owner (yang juga merupakan staf) tidak dapat mencatatkan kehadiran di sesi harian otomatis karena dianggap membuka sesi sendiri.

## 2. Solusi yang Diterapkan
1. **Restorasi `opened_by` Valid dengan Fallback Dinamis (`bot/jobs.py`)**:
   - Mengembalikan penetapan `opened_by` pada `daily_staff_attendance_open` ke `OWNER_ID` yang valid (terdaftar di tabel `users` sebagai role `owner`).
   - Menambahkan fallback dinamis ke akun owner/admin pertama di database jika `OWNER_ID` kosong di environment:
     ```python
     if not opened_by:
         from bot.settings import OWNER_ID
         opened_by = OWNER_ID
         if not opened_by:
             cur = await conn.execute("SELECT telegram_id FROM users WHERE role = 'owner' LIMIT 1")
             r = await cur.fetchone()
             if r:
                 opened_by = int(r["telegram_id"])
     ```
2. **Mekanisme Pemulihan Sesi Basi Otomatis (Stale Session Recovery)**:
   - Menambahkan pengecekan usia sesi aktif pada `daily_staff_attendance_open` dan `daily_maba_attendance_open`.
   - Jika sesi aktif yang ditemukan telah dibuka lebih dari 16 jam yang lalu (berasal dari hari sebelumnya), sistem secara otomatis menutup sesi basi tersebut dan me-refresh pengumumannya sebelum melanjutkan membuka sesi baru yang segar untuk hari ini.
   - Membungkus seluruh alur pembukaan dan penutupan dalam blok `try...except` dengan pencatatan log lengkap (`log.error`) agar jika terjadi error, stack trace dapat segera ditelusuri.
3. **Pengecualian Self-Attendance untuk Sesi Otomatis (`bot/handlers/attendance.py`)**:
   - Menambahkan `staff_auto` dan `maba_auto` ke dalam daftar pengecualian di `_record_hadir`:
     ```python
     if int(sess.get("opened_by") or 0) == uid and sess["class_id"] not in (
         "staff_auto", "maba_auto", "staff_manual", "bem_manual", "event_bebas"
     ):
         return False, "Anda tidak perlu mengisi presensi untuk sesi yang Anda buka sendiri.", False
     ```
   - Dengan ini, Owner atau staf yang membuka sesi otomatis tetap berhak mencatatkan kehadiran sebagai peserta staf tanpa hambatan otorisasi.
4. **Pengujian Unit Test**:
   - Menambahkan skenario komprehensif `test_daily_staff_attendance_lifecycle_and_stale_recovery` di `tests/test_auto_close_presensi.py`:
     - Verifikasi eksekusi `daily_staff_attendance_open` dengan `opened_by=None` (alur cron) berhasil membuat sesi tanpa pelanggaran FK.
     - Verifikasi kehadiran Owner pada `staff_auto` berhasil tercatat.
     - Verifikasi idempotensi pemanggilan ulang sesi segar (< 16 jam).
     - Verifikasi pemulihan sesi basi (> 16 jam) yang otomatis menutup sesi kemarin dan membuka sesi baru.
     - Verifikasi penutupan sesi harian melalui `daily_staff_attendance_close`.

## 3. Hasil Pengujian
- `tests/test_auto_close_presensi.py`: **3/3 PASSED** (100%).
- `tests/test_presensi.py`: **1/1 PASSED** (100%).
- Zero regression pada sistem presensi manual, UKM, kelas umum, dan proteksi penutupan sesi otomatis.
