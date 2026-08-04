# Task 010: Alur Pendaftaran Akun Publik & Integrasi Maba

## Apa yang Dikerjakan?
1. Menambahkan tombol **"Daftar Akun Publik"** pada menu `/start` untuk role `public`.
2. Mengecualikan field `muse` dan `birth_date` agar tidak wajib bagi pengguna publik (role `public`).
3. Mengubah respon penebusan kode akses (gencode) untuk role `maba`, agar memberikan *link* grup secara instan apabila pengguna tersebut sebelumnya sudah pernah melengkapi profil sebagai akun publik.

## Mengapa Dikerjakan?
- **User Experience (UX):** Memungkinkan pengguna non-mahasiswa (publik) untuk langsung mendaftarkan nama mereka dan menggunakan fitur bot (misal: Menfess) tanpa dihalangi oleh form data yang panjang.
- **Fleksibilitas Role:** Pengguna yang awalnya hanya "Coba-coba" sebagai akun publik, nantinya bisa meng-upgrade akun mereka menggunakan Kode Akademik (misal jadi `maba` atau `student`).
- **Pencegahan Bug Transisi:** Sebelumnya, pengguna yang telah berstatus *lengkapi_done* sebagai `public`, ketika menebus kode `maba` akan terjebak karena mereka tidak bisa `/lengkapi` lagi, sehingga *link* MABA gagal terkirim. Fitur baru ini mendeteksi kondisi tersebut dan mengeksekusi penyerahan *link* secara langsung saat penebusan.

## Teknis Pelaksanaan
- **`config/profile_fields.yaml`**: Modifikasi daftar *roles* pada field `muse` & `birth_date` untuk mengecualikan `public`. Kini, field `full_name` yang otomatis di-*fallback* untuk semua *roles* adalah satu-satunya syarat mutlak bagi `public`.
- **`bot/handlers/commands.py`**: Menyelipkan tombol *inline* ber-callback `openlt:full_name` jika fungsi `_is_lengkapi_done(profile)` me-return False. Tombol diletakkan di atas "Pakai Kode Akademik" di `cmd_start` dan `action == "back"`.
- **`bot/handlers/messages.py`**: Di blok kode eksekusi `maba`, ditambahkan validasi ulang profil dengan `_is_lengkapi_done(prof_u)`. Jika memenuhi syarat, skrip akan mengabaikan perintah "Silakan lengkapi profil" dan langsung merender *link* dari list `MABA_GROUP_LINKS`.
