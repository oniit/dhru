# 054: Full Code Audit Fixes V2

## Apa yang dikerjakan?
- **Perbaikan HTML Injection/XSS (Telegram ParseMode DoS)**: Menambahkan `html.escape()` pada input/text berbasis user di `bot/handlers/tugas.py` dan `bot/handlers/attendance.py`.
- **Perbaikan Indentation Error di checker**: Merapikan import dan memperbaiki `IndentationError` / *SyntaxError* yang menyebabkan crash di fitur background Pyrogram `bot/checker.py`.
- **Perbaikan Un-Awaited Task Coroutine**: Menggunakan `asyncio.create_task` di `bot/handlers/broadcast.py` agar PTB background task tidak menghasilkan `RuntimeWarning` dan berjalan lancar.
- **Perbaikan Limit/Offset Negatif**: Menambahkan pengecekan `and int(token) > 0` di `bot/handlers/commands.py` untuk menghindari `OFFSET -1` saat user mengeksekusi `/profile 0`.
- **Perbaikan Penanganan Eksepsi (Race Condition)**: Menangkap `aiosqlite.IntegrityError` (bukan umum `Exception`) di `bot/database.py` saat mengurus *Race Condition* di `record_attendance` dan `submit_task`.

## Mengapa dikerjakan?
- Hasil audit ekstensif (*Full Code Audit*) sebelumnya mengonfirmasi adanya bug krusial yang bisa berdampak pada operasional harian bot. Misalnya celah *HTML Parsing* Telegram dapat disalahgunakan untuk DOS ringan pada channel pengumuman atau DM instruktur, sementara _indentation error_ pasti mengakibatkan proses checker Pyrogram lumpuh.

## Alur teknis
- **tugas.py & attendance.py**: Mengimpor modul `html` bawaan Python. Memanggil `html.escape()` pada nama mahasiswa (`sname`, `student_name`), teks deskriptif matkul (`c_lab`), dan judul tugas (`task['title']`) sebelum dimasukkan ke `f-string` yang akan dikirim bot.
- **checker.py**: Membersihkan deklarasi berulang dari `import requests` dan `import asyncio` di dalam *for-loop*. Skrip diposisikan ulang dengan `await asyncio.to_thread` tanpa melanggar blok *indentation* Python.
- **database.py**: Pengubahan dari `except Exception:` ke `except aiosqlite.IntegrityError:` mencegah *swallowing* pada I/O error atau Network error jika terjadi putus koneksi ke database.
