# Update MABA Groups

## Ringkasan
Menambahkan nama kelompok maba ke dalam sistem alih-alih hanya menggunakan angka "Kelompok 1", "Kelompok 2", dst. Nama-nama tersebut adalah:
1. Pramoerdita
2. Nusapraja
3. Candrakirana
4. Purnawijaya

## Latar Belakang
User telah menentukan 4 nama grup yang akan dialokasikan kepada maba, sehingga pesan konfirmasi atau verifikasi harus menggunakan nama tersebut, bukan angka mentahnya. 

## Detail Perubahan
1. Menambahkan `MABA_GROUP_NAMES` dictionary di `bot/settings.py` yang memetakan angka 1-4 ke nama kelompok.
2. Memodifikasi penggunaan variabel `maba_group` (yang sebelumnya hanya berupa integer) pada pesan-pesan balasan di `bot/handlers/messages.py` dan `bot/handlers/commands.py` untuk menggunakan nama kelompok lewat metode `.get(mg, mg)` dari dictionary `MABA_GROUP_NAMES`.
3. Memodifikasi `role_display` / print profil di `bot/handlers/common.py` agar profil pengguna menampilkan nama kelompok MABA.
