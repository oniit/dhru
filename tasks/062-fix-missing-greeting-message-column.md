# Fix KeyError 'greeting_message' pada bot_chats di Production (Turso)

## Latar Belakang
User melaporkan bahwa perintah `/greeting` dan sistem pesan selamat datang (greeting message) berjalan dengan baik di environment lokal (dev), namun menyebabkan bot gagal/berhenti (crash) saat dijalankan di production yang menggunakan Turso.

## Akar Masalah
Masalah disebabkan oleh absennya migrasi kolom `greeting_message` pada database production Turso. Meskipun `SCHEMA` di `bot/database.py` telah diperbarui dengan `CREATE TABLE IF NOT EXISTS bot_chats`, perintah tersebut akan diabaikan oleh SQLite/Turso apabila tabel `bot_chats` sudah ada. 

Karena `AiosqliteRowMock` di `bot/database.py` (yang dipakai untuk Turso) akan menghasilkan `KeyError` secara eksplisit apabila kita mencoba mengakses *key* yang tidak ada dalam hasil query, mengakses `chat_data["greeting_message"]` pada tabel yang tidak memiliki kolom tersebut akan menyebabkan program error setiap kali `cmd_greeting` atau *handler* *chat member* dipanggil.

Di environment dev (lokal), ini bekerja karena file `bot.db` kemungkinan dihapus dan di-recreate dengan schema baru, atau bermigrasi secara manual, sehingga kolom tersebut eksis dan query `SELECT * FROM bot_chats` berjalan normal.

## Perubahan yang Dilakukan
- Menambahkan prosedur migrasi skema tabel di `bot/database.py` menggunakan `PRAGMA table_info(bot_chats)`.
- Jika didapati bahwa kolom `greeting_message` belum ada di hasil query *pragma*, bot akan otomatis mengeksekusi `ALTER TABLE bot_chats ADD COLUMN greeting_message TEXT` saat inisialisasi koneksi.
