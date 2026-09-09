# Task 069: Menyembunyikan Tombol Daftar Akun Maba

## Deskripsi
User meminta untuk menyembunyikan sementara tombol **"Daftar Akun Mahasiswa Baru"** pada menu awal publik, tanpa menghilangkan fungsi maupun logika _backend_ yang memproses pendaftaran tersebut.

## Alasan
Untuk sementara waktu menghentikan masuknya _user_ baru yang mendaftar via tombol UI (UX) di _bot_, namun _flow_ pendaftaran itu sendiri dan kode-kode terkait tetap dibiarkan utuh di basis data dan skrip agar sewaktu-waktu bisa ditampilkan kembali dengan mudah tanpa menulis ulang kodenya.

## Perubahan Teknis
- Memodifikasi `bot/handlers/commands.py` untuk mengomentari (`comment out`) baris kode yang melakukan proses _append_ tombol "Daftar Akun Mahasiswa Baru" (`callback_data="maba:start"`) ke dalam _list_ `buttons`.
- Hal ini dilakukan pada dua tempat (baris awal perintah `/start` dan _callback_ "Kembali" dari menu instansi).
- Kode penanganan `maba:start` pada `bot/handlers/messages.py` dan bagian _callback query_ tidak diubah, sehingga fungsi sistemik tetap aman.

## File yang Diubah
- `bot/handlers/commands.py`
