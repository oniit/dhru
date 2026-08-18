# 029 - Menambahkan Perintah `/kode` dan Bonus Agra untuk MABA

## Apa yang Dikerjakan
1. Membuat perintah baru `/kode` pada `bot/handlers/commands.py` untuk memicu proses `INPUT_CODE`.
2. Mendaftarkan perintah `/kode` tersebut di `bot/handlers/register.py`.
3. Menambahkan logika pada langkah `MABA_NAME` di `bot/handlers/messages.py` sehingga saat Maba selesai mengisi nama, mereka akan secara otomatis menerima bonus Agra, sama halnya seperti proses pelengkapan data (`TEXT_LC`).

## Mengapa Dikerjakan
1. **Perintah `/kode`**: Akun dengan peran (_role_) selain `ROLE_PUBLIC` (termasuk MABA) sebelumnya tidak dapat melihat menu pendaftaran awal via `/start`, sehingga tombol "Pakai Kode Akademik" tidak muncul untuk mereka. MABA yang ingin mengganti/memasukkan kode (misalnya _gencode_) kesulitan. Dengan `/kode`, pengguna bisa langsung melompat ke proses input kode dari mana pun mereka berada tanpa harus menekan tombol awal.
2. **Bonus Agra MABA**: Menambahkan pemanggilan fungsi `award_lengkapi_agra` saat MABA mengisi nama, agar sistem _reward_ Agra berjalan seimbang dan mengapresiasi kelengkapan profil dasar, layaknya ketika mengisi profil melalui proses `/lengkapi`.

## Bagaimana Alur Kodenya Bekerja
1. Perintah `/kode` mengubah _state_ `onboarding_step` ke `INPUT_CODE`. 
2. Pada pesan pendaftaran `MABA_NAME`, program sekarang menggunakan `profile_from_row` untuk mengekstrak profil lama sebelum memperbarui `full_name`.
3. Setelah memperbarui baris tabel, ia akan memanggil fungsi eksternal `award_lengkapi_agra` yang menghitung apakah tambahan field `full_name` layak mendapatkan imbalan Agra dan memberikannya jika ya.
