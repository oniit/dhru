# 085 - Fix Presensi UKM (Unit Kegiatan Mahasiswa)

## Latar Belakang
User menemukan celah masalah baru ketika seorang Shishya mencoba presensi (hadir) pada sesi UKM (Klub). Pesan error yang muncul adalah *"Sesi ini di luar akses presensi kamu."*

## Penyebab (Root Cause)
Secara arsitektur, ID sesi UKM (contohnya `um` untuk Klub Memasak, `ui` untuk Klub Bahasa Inggris) memang valid dan bisa dibuka sebagai sesi presensi oleh admin.
Namun, fungsi `classes_for_presensi(profile)` di `bot/handlers/attendance.py` sebelumnya hanya menggabungkan kelas akademik dari fungsi `get_automatic_classes(profile)` dan kelas mengajar dari `teaching_classes`.
Field `club_enrolled` **tidak ikut dibaca/diextract**, sehingga daftar `user_classes` milik mahasiswa tidak pernah menyertakan ID kelas UKM yang diikutinya. Akibatnya, validasi mencocokkan `sess["class_id"]` dengan `user_classes` selalu gagal (False) untuk sesi UKM.

## Perbaikan
1. Mengubah `classes_for_presensi(profile)` di `bot/handlers/attendance.py`:
   - Mengekstrak data `club_enrolled` dari profil pengguna: `clubs = normalize_multi_choice_value(profile.get("club_enrolled"))`
   - Menggabungkannya ke dalam list return: `return list(dict.fromkeys(enrolled + teaching + clubs))`
2. (Maintenance) Membatalkan (revert) logika pengecekan *"d_sekre"* yang redundan di `cmd_hadir` dan `cb_attendance_action`, karena user dengan `d_sekre` dipastikan secara profil selalu memegang *role* Staf Inti (`owner`, `admin`, atau `internal`), sehingga mereka otomatis sudah diloloskan melalui pengecekan `row["role"] in (ROLE_INTERNAL, ROLE_ADMIN, ROLE_OWNER)`.
