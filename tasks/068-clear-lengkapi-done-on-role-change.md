# Task: Clear Profile Complete State on Role Change

## Latar Belakang
User menemukan bug/perilaku di mana jika seseorang berganti *role* (misal: maba ke student, atau student ke internal) dan *role* barunya mewajibkan field baru (misal: jabatan, kelas), status profilnya tetap dianggap "lengkap" (karena *flag* `__lengkapi_done` tidak pernah dihapus). Hal ini menyebabkan user bisa melewati tahapan pengisian data wajib di role barunya, kecuali mereka sengaja memanggil perintah `/lengkapi` lagi.

## Pekerjaan yang Dilakukan
- Menambahkan pemeriksaan field wajib secara otomatis saat metode `set_role` dipanggil di tingkat *database*.
- Menghapus flag `__lengkapi_done` dari JSON profil user jika hasil validasi field untuk role yang baru menunjukkan masih ada data wajib yang kosong.

## Teknis
- Modifikasi fungsi `set_role` pada `bot/database.py`.
- Setelah mengambil *profile_dict* dan melakukan *apply generated fields*, fungsi akan meng-import `missing_required_fields` dari `bot.handlers.common`.
- Fungsi akan memanggil `missing_required_fields(current, role)`. Jika tidak kosong (artinya ada *required field* yang belum diisi), maka `current.pop("__lengkapi_done", None)` dieksekusi sebelum melakukan *commit* ke database.
- Impor diletakkan di dalam fungsi (`local import`) untuk mencegah *circular import* karena `bot.handlers.common` bergantung pada `bot.database`.
