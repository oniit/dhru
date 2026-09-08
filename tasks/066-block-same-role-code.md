# Task 066: Block Same Role Code Input

## Deskripsi
Menambahkan validasi pada input kode akses agar jika peran yang didapatkan dari kode tersebut sama dengan peran user saat ini, maka kode tersebut ditolak dan tidak digunakan.

## Alasan
Menghindari penggunaan kode akses yang sia-sia oleh user yang sudah memiliki peran yang sama dengan kode tersebut, sehingga kode tetap bisa digunakan oleh orang lain atau di waktu yang lain jika diperlukan.

## Teknis
- Memodifikasi file `bot/handlers/messages.py` pada bagian penanganan `step == "INPUT_CODE"`.
- Menambahkan pengecekan `if row["role"] == target_role:`.
- Jika sama, bot akan mengirimkan pesan `gagal, ini adalah kode {target_role}, peranmu sebelumnya {row['role']}`, menghapus status `onboarding_step` menjadi `None`, dan membatalkan query update penggunaan kode.
