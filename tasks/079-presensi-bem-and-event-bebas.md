# 079 - Penambahan Presensi BEM dan Event Bebas

## Latar Belakang
User meminta tambahan jenis presensi:
1. Satu jenis presensi yang bisa dibuka oleh semua role (kecuali `public`) tanpa memberikan bonus Agra.
2. Presensi khusus untuk role BEM / Yaksa.

## Perubahan yang Dilakukan
- Menambahkan ID kelas `bem_manual` (Presensi BEM / Yaksa) dan `event_bebas` (Event Umum).
- Memperbarui fungsi `presence_allowed_class_ids` di `bot/handlers/common.py` agar:
  - Role BEM mendapatkan akses membuka presensi `bem_manual`.
  - Semua role yang terdaftar (bukan `public`) mendapatkan akses membuka presensi `event_bebas`.
- Menambahkan pilihan keyboard untuk dua tipe presensi ini di `_classes_keyboard` dalam `bot/handlers/attendance.py`.
- Menambahkan pengecualian bonus Agra (memberikan 0 Agra) saat pengguna mengisi presensi untuk `event_bebas`.
- Memperbarui pengecekan `can_rekap_hadir_session` agar BEM bisa merekap presensi BEM mereka, dan user non-public bisa merekap presensi `event_bebas`.

## Alur Kerja Teknis
- Saat command `/presensi buka` dieksekusi, sistem mengecek akses lewat `presence_allowed_class_ids`. Karena `event_bebas` masuk untuk semua non-public, semua user terdaftar lolos pengecekan ini dan memunculkan tombol "Event Umum (Bebas)".
- Untuk BEM, tambahan tombol "BEM / Yaksa" akan muncul.
- Saat `/presensi hadir` atau klik inline button, ID kelas ditambahkan ke profil virtual di fungsi saat rekap. Jika user mengisi form untuk `event_bebas`, logic akan bypass penambahan Agra di `_record_hadir`.
