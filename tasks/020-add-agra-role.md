# Task 020: Fitur Pemberian Agra Berdasarkan Role

## Tujuan
Memungkinkan Administrator atau Owner untuk memberikan poin Agra (atau menguranginya) kepada semua pengguna dalam suatu peran (role) tertentu secara masal menggunakan perintah `/add`.

## Detail Implementasi
1. **Pembaruan Parser (`bot/agra_parse.py`)**:
   - Fungsi `parse_add_command` diperbarui agar tidak hanya mendeteksi `@username` atau _reply_, tetapi juga mendeteksi sebuah kata utuh (misal `internal`, `student`) sebelum angka nominal.
   - Variabel baru `target_role` ditambahkan pada `ParsedAdd`.
   - Pola Regex disesuaikan menjadi `^/(?:add|transfer)(?:@\S+)?\s+(?:([a-zA-Z_]+)\s+)?(-?\d+)\s*`.
2. **Pembaruan Handler (`bot/handlers/commands.py`)**:
   - Di dalam `cmd_add`, ditambahkan logika untuk memeriksa apakah `parsed.target_role` merupakan role yang valid di dalam `ROLES_ORDER` (seperti `student`, `internal`, `admin`, dll).
   - Jika valid, bot akan melakukan _query_ ke SQLite `SELECT telegram_id FROM users WHERE role = ?` untuk mengambil semua ID pengguna dalam role tersebut dan menggabungkannya dengan `targets`.
   - Transaksi pemberian poin Agra tetap menggunakan `db.add_agra` secara individual di dalam _loop_ sehingga notifikasi DM terkirim ke masing-masing pengguna.
3. **Dokumentasi (`docs/commands.md`)**:
   - Perintah `/add` akhirnya didokumentasikan di bawah bagian **Manajemen**.

## Hasil
Pengguna kini bisa melakukan `/add internal 50 | Bonus akhir bulan` atau `/add student -10 | Hukuman`. Hal ini berlaku untuk `/add`, sedangkan perintah `/transfer` yang berbagi parser yang sama tetap aman karena tidak mengimplementasikan pengumpulan target berbasis role.
