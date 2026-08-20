# 034 Command Reload Bot

## Deskripsi
Menambahkan command `/reload` agar Owner/Admin dapat memulai ulang bot langsung dari obrolan Telegram.

## Alasan
Mempermudah admin atau founder dalam menerapkan pembaruan (restart) bot tanpa harus login ke _terminal server_ secara manual dan menjalankan perintah `systemctl restart botdhru`.

## Implementasi Teknis
- Menambahkan fungsi baru `cmd_reload` di file `bot/handlers/commands.py`.
- Mendaftarkan handler `CommandHandler("reload", commands.cmd_reload)` di dalam `bot/handlers/register.py`.
- Melakukan pengecekan `ROLE_OWNER` dan `ROLE_ADMIN` sebelum perintah dieksekusi.
- Mengeksekusi command tingkat OS melalui `os.system("sudo systemctl restart botdhru")`.
- **Notifikasi Pasca-Restart**: Sebelum dieksekusi, bot menyimpan info ID pesan dan obrolan ke `.restart.json`. Saat bot berhasil menyala kembali, fungsi `post_init` di `main.py` akan mengedit pesan tersebut menjadi ✅ **Bot berhasil dimulai ulang** agar admin tahu restart telah selesai.
- Memperbarui `docs/commands.md` dengan menambahkan command `/reload` ke dalam daftar manajemen.
