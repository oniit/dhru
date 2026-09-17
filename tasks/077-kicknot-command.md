# Task 077: Fitur Kick Berdasarkan Pengecualian Role (/kicknot)

## Deskripsi
Menambahkan fitur `mass-kick` untuk mengeluarkan semua anggota dari suatu grup yang **tidak** memiliki setidaknya satu role yang disebutkan (pengecualian). Ini berguna untuk membersihkan grup (misalnya dari akun publik, spammer, atau role lain yang tidak relevan) secara otomatis tanpa perlu melakukannya satu persatu.

## Perubahan Kode
- **`bot/handlers/commands.py`**:
  - Menambahkan fungsi `async def cmd_kicknot(update, context)`.
  - Fungsi ini meminta data semua member dari `userbot` menggunakan mekanisme IPC di database `userbot_requests`.
  - Melakukan perulangan, mengecek `role` setiap member di database, dan mengeluarkan mereka yang tidak ada di dalam daftar argumen role.
  - Role `owner` dan `admin` dijamin aman karena selalu ditambahkan secara otomatis ke dalam `allowed_roles`.
  - Memberikan 1 pesan rekapitulasi di akhir eksekusi (tanpa spam notifikasi kick satu persatu).
- **`bot/handlers/register.py`**: Mendaftarkan `CommandHandler("kicknot", commands.cmd_kicknot)`.
- **`docs/commands.md`**: Mendokumentasikan perintah `/kicknot <role1> <role2>...`.

## Alasan / Konteks
Fitur ini diminta oleh user untuk memudahkan manajemen anggota di dalam grup internal sehingga staf tidak perlu secara manual men-kick member yang bukan bagian dari internal/student.
