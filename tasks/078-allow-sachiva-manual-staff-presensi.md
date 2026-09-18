# Allow Sachiva to Open Manual Staff Presensi

## Deskripsi
Fitur kecil untuk mengizinkan staf dengan jabatan Sachiva (Sekretaris / `d_sekre`) agar dapat melihat tombol "Staf" dan membuka sesi presensi staf secara manual (`staff_manual`) pada menu `/presensi buka`.

## Kenapa Dikerjakan?
Atas permintaan user agar staf dengan jabatan Sachiva bisa membuka presensi staf secara manual, karena sebelumnya tombol dan perizinan tersebut secara ketat dibatasi hanya untuk _role_ `owner` dan `admin`.

## Alur Kode Secara Teknis
1. Di `bot/handlers/common.py` (pada fungsi `presence_allowed_class_ids`), ketika pengguna memiliki jabatan `d_sekre`, nilai `"staff_manual"` ditambahkan ke dalam himpunan ID kelas yang diizinkannya (`ids.extend(["staff_auto", "staff_manual"])`).
2. Di `bot/handlers/attendance.py` (pada fungsi `_classes_keyboard`), logika pembuatan tombol "👥 Staf" dimodifikasi agar turut mengecek jika `"staff_manual" in allowed_set` (selain memeriksa `allowed_set is None`). Dengan demikian, pengguna dengan izin terbatas yang spesifik memiliki akses ke `"staff_manual"` (seperti Sachiva) kini akan melihat tombol tersebut di antarmuka Telegram.
