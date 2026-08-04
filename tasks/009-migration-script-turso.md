# Migration Script to Turso

## Deskripsi Task
User menyadari bahwa selama ini bot di VPS berjalan menggunakan database lokal SQLite karena lupa memasukkan link Turso ke dalam `.env`. Oleh karena itu, diperlukan cara untuk memigrasi seluruh data dari database lokal VPS (`data/bot.db`) ke database remote Turso yang baru agar tidak ada data yang hilang dan bot bisa menggunakan Turso ke depannya.

## Apa yang Dikerjakan
- Membuat skrip `migrate_vps_to_turso.py`.
- Skrip ini bertugas:
  1. Membaca `TURSO_DB_URL` dan `TURSO_AUTH_TOKEN` dari file `.env`.
  2. Membuka koneksi ke database lokal SQLite di `data/bot.db`.
  3. Membuka koneksi ke Turso menggunakan `libsql_client`.
  4. Membuat tabel-tabel di Turso jika belum ada (berdasarkan `SCHEMA` di `bot/database.py`).
  5. Mengambil daftar semua tabel dari database lokal.
  6. Mengambil semua baris dari setiap tabel, lalu memindahkannya menggunakan query `INSERT OR REPLACE` ke database Turso.
- Memperbarui dokumentasi `docs/database.md` untuk memberikan informasi seputar migrasi ke Turso.

## Cara Kerja Teknis
- Skrip berjalan menggunakan `asyncio`.
- SQLite membaca baris dalam bentuk dictionary (dengan `sqlite3.Row`), sehingga memudahkan pengambilan kunci kolom.
- Nilai di-insert secara iteratif ke tabel yang sesuai di Turso. Penggunaan `INSERT OR REPLACE` memastikan jika data sudah ada, akan tertimpa dengan yang terbaru dari VPS.
