# 046 - Mini-Games Settings CRUD Commands

## Apa yang Dikerjakan
Menambahkan fungsionalitas komplit CRUD (Create, Read, Update, Delete) untuk manajemen pengaturan mini-games (terutama Kata Rahasia) dengan menambah fungsi pembacaan dan penghapusan konfigurasi _game_ yang tersimpan di _database_.

## Mengapa Dikerjakan
Sebelumnya, *admin* hanya bisa membuat atau memperbarui _setting_ kata (misalnya `/atur kata_rahasia panitia ...`). Namun, tidak ada cara untuk melihat daftar pengaturan (_setting_) apa saja yang pernah dibuat dan tidak ada cara untuk menghapusnya dari _database_ tanpa akses langsung ke _file database_. Sesuai permintaan pengguna, ditambahkan perintah untuk mengelola manajemen *game settings* ini dari antarmuka _bot_.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. Di dalam `bot/database.py`, fungsi `get_all_game_settings(self, conn, game_name)` ditambahkan untuk menarik semua nama _setting_ unik dari tabel `game_settings` milik `game_name` tertentu.
2. Di dalam `bot/database.py`, fungsi `delete_game_setting(self, conn, game_name, setting_name)` ditambahkan untuk mengeksekusi `DELETE` dari tabel.
3. Di `bot/handlers/games.py`, _command handler_ baru ditulis:
   - `cmd_hapus_setting`: Mengakses `delete_game_setting` lalu memberikan pesan konfirmasi apabila berhasil terhapus atau pesan _error_ bila _setting_ tidak ditemukan. Handler ini dijaga dengan _permission check_ `_is_admin`.
   - `cmd_cek_setting`: Mengakses `get_all_game_settings` lalu menampilkan daftarnya (misal: "panitia", "desa17an") ke dalam format _list markdown_.
4. Kedua handler tersebut didaftarkan pada _dispatcher_ di `bot/handlers/register.py` sebagai `CommandHandler("hapus_setting", ...)` dan `CommandHandler("cek_setting", ...)`.
5. Terakhir, `docs/commands.md` diperbarui agar menyertakan referensi perintah-perintah baru ini di bagian Mini Games.
