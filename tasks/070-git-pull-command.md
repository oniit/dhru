# Task 070: Menambahkan Perintah `/pull` untuk Git Pull

## Deskripsi
User meminta fitur baru untuk mengeksekusi `git pull` secara langsung dari Telegram via bot, agar memudahkan penarikan pembaruan kode terbaru dari repositori GitHub tanpa harus membuka SSH/Terminal ke server.

## Implementasi
1. Menambahkan fungsi `cmd_pull` pada `bot/handlers/commands.py`.
2. Fungsi ini memanfaatkan modul `subprocess` bawaan Python untuk memanggil `subprocess.run(["git", "pull"], ...)`.
3. Fungsi tersebut menangkap hasil standard output (`stdout`) dan standard error (`stderr`), kemudian menampilkannya kembali ke user. Jika output dari `git pull` kosong, maka ia merespons dengan format standar seperti yang diharapkan (atau error jika gagal).
4. Fungsi dibatasi hanya untuk _role_ `ROLE_OWNER` dan `ROLE_ADMIN` menggunakan validasi database pada awal fungsi.
5. Menambahkan register _handler_ perintah `pull` (`CommandHandler("pull", commands.cmd_pull)`) ke dalam berkas `bot/handlers/register.py`.
6. Memperbarui `docs/commands.md` dengan menyisipkan detail `/pull` ke dalam daftar manajemen (_Management_).

## File yang Diubah
- `bot/handlers/commands.py`
- `bot/handlers/register.py`
- `docs/commands.md`
