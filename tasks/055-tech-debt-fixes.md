# 055: Tech Debt & Optimasi

## Apa yang dikerjakan?
- **Sistem Antrean Broadcast (`broadcast.py`)**: Merombak loop pengiriman `/broadcast` dari sekadar `asyncio.sleep(1)` statis menjadi antrean (queue) yang mem-parsing exception `telegram.error.RetryAfter`. Ini mencegah bot dari terkena sanksi *FloodWait* jika menyiarkan pesan ke ribuan akun secara konstan.
- **Parser SQL executescript (`database.py`)**: Menghilangkan rekursi internal `sqlite3.complete_statement` yang rawan _stuck_ atau lambat dalam membaca string kueri panjang, dan menggantinya dengan pemisah baris `.split(";")` yang lebih _robust_ dan ringan.

## Mengapa dikerjakan?
- Pembaruan ini di-*request* langsung untuk menutup seluruh temuan _Full Code Audit_ agar _tech debt_ dapat dilunasi 100% sebelum naik ke _production_. 

## Alur teknis
- Di `broadcast.py`, fungsi `run_broadcast` dieksekusi via task background (`asyncio.create_task`). Loop di dalamnya diubah untuk menggunakan logika `while True:` per penerima. Jika blokir `RetryAfter` muncul, fungsi mengekstrak nilai `retry_after` dan `asyncio.sleep` tepat selama durasi blokir, sebelum me-retry.
- Di `database.py`, parameter SQL Script pada method `AiosqliteConnectionMock.executescript` dipisah melalui List Comprehension `[s.strip() for s in sql_script.split(";") if s.strip()]` sehingga secara instan mengubah string menjadi _List of Statements_ yang aman dikirim ke Turso/DB lokal.
