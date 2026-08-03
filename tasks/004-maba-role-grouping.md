# Task 004: Implementasi Role MABA dan Pembagian Grup

## Deskripsi
Menambahkan fitur pendaftaran mahasiswa baru (MABA) menggunakan access code (gencode), lalu mengurutkannya secara *round-robin* ke dalam 4 kelompok. Setelah Maba berhasil memasukkan data namanya, bot akan memberikan link grup sesuai kelompok mereka.

## Perubahan Kode
1. **`bot/database.py`**: Menambahkan konstanta `ROLE_MABA` dan memposisikannya dalam urutan `ROLES_ORDER`.
2. **`bot/settings.py`**: Melakukan parsing `MABA_GROUP_1` hingga `MABA_GROUP_4` dari `.env`.
3. **`config/profile_fields.yaml`**: Memastikan Maba hanya diwajibkan untuk mengisi field `full_name`. Field lain seperti `muse` dan `birth_date` dikhususkan untuk role lain, sementara field khusus Maba `maba_group` juga ditampilkan di UI.
4. **`bot/handlers/commands.py`**: Membuka blokir pembuatan gencode khusus target role `maba`.
5. **`bot/handlers/messages.py`**: 
   - Ketika Maba memasukkan gencode valid, sistem akan mencari urutan gencode maba tersebut (berapa banyak gencode Maba yang sudah diklaim sebelumnya). Urutan ini di-modulo dengan 4 untuk menghasilkan nomor `maba_group` (1-4).
   - Di blok `/lengkapi`, ketika pengguna selesai menginput namanya, apabila mereka `maba`, bot akan merender balasan berisi ucapan selamat dan menempelkan link grup yang sesuai.
6. **`bot/handlers/common.py`**: Menyesuaikan fungsi `role_display` dan fungsi cetak profil agar field internal `maba_group` bisa dirender rapi untuk diperiksa.

## Validasi
- Round-robin dipastikan *race-condition free* karena `SELECT COUNT(*)` merujuk ke tabel `access_codes` `used_at` yang telah terkunci (atomic sequence check for the specific user's code).
- User MABA tidak perlu direpotkan dengan field yang terlalu panjang (hanya satu field yang dibuka untuk lengkapi).
