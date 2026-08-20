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
- Memperbarui `docs/commands.md` dengan menambahkan command `/reload` ke dalam daftar manajemen.
