# Perintah Daftar Kelompok Maba

## Deskripsi
Fitur ini menambahkan opsi baru pada perintah `/daftar` untuk memfilter pengguna maba (pravesi) berdasarkan kelompok spesifik. Sebelumnya, fitur untuk melihat daftar per kelompok belum didukung; admin hanya dapat melihat total seluruh maba melalui `/daftar pravesi`.

Dengan ekstensi ini, argumen akan menerima nama kelompok (bukan ID angka), sehingga pencariannya akan lebih intuitif secara lisan/nama kelompoknya.

## Detail Implementasi
- Di `bot/handlers/commands.py` pada fungsi `cmd_daftar`:
  - Ditambahkan dukungan argumen opsional `kelompok <nama_kelompok>`.
  - Sistem akan mencocokkan input `<nama_kelompok>` tersebut (secara *case-insensitive*) dengan yang terdaftar di `MABA_GROUP_NAMES` di dalam file `bot/settings.py`.
  - Jika argumen yang dimasukkan adalah `belum` (`/daftar kelompok belum`), bot akan memfilter dan menampilkan daftar pengguna dengan role `maba` yang sama sekali belum memiliki properti `maba_group` (belum diplot).
  - Jika cocok dengan nama kelompok, sistem akan mengambil nilai ID aslinya, lalu mengiterasi seluruh pengguna dengan role `maba` yang nilai `maba_group`-nya sesuai dengan ID tersebut.
  - Opsi perintah ini (`/daftar kelompok <nama_kelompok>` dan `/daftar kelompok belum`) telah disisipkan juga ke dalam pesan *help* balasan bawaan.
