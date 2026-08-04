# Task 011: Perbaikan Kerentanan Race Condition & Transaksi (QA Audit)

## Deskripsi
Melakukan perbaikan atas temuan audit dari peran Senior QA mengenai celah keamanan di tingkat arsitektur (TOCTOU - *Time of Check to Time of Use*) pada manajemen saldo Agra dan evaluasi transaksi database (khususnya untuk Turso).

## Detail Pekerjaan
1. **Pencegahan Infinite Money Glitch (Menfess):**
   - Menambahkan fungsi `deduct_agra_if_sufficient` di `database.py` menggunakan query `INSERT INTO ... SELECT ... WHERE (SELECT SUM(amount)...) >= ?`.
   - Modifikasi `bot/handlers/menfess.py` untuk memanggil pengurangan atomik ini di awal sebelum pesan dikirim ke channel.
   - Mengimplementasikan fitur *rollback manual* via penambahan saldo (refund) apabila bot gagal mengirim menfess ke channel.
2. **Atomic Task Review & Presensi:**
   - Memodifikasi `review_submission` di `database.py` agar tidak melakukan `SELECT` lalu `UPDATE`, melainkan `UPDATE ... WHERE status = 'submitted'` lalu me-return nilai berdasarkan `rowcount`. Hal ini mencegah admin memberikan poin Agra berlipat ganda akibat double-click.
   - Memodifikasi `record_attendance` agar kebal dari race condition dengan pola `UPDATE` jika `INSERT` (yang memiliki constraint unik) gagal, dengan pengembalian status berdasarkan `rowcount`.
3. **Perbaikan SQL Parser (Turso Mock):**
   - Menulis ulang metode `executescript` pada `AiosqliteConnectionMock` untuk menggunakan `sqlite3.complete_statement` atau API `.batch()` dari `libsql_client`, mencegah terpotongnya query SQL di karakter `;` (titik koma) yang berada di dalam string literal.

## Mengapa ini dikerjakan?
- Bot rawan mengalami pencetakan poin Agra ilegal oleh oknum yang me-request proses menfess secara konkuren (menggunakan *spammer tools*). 
- Modul mock Turso memiliki sifat per-statement autocommit (mengabaikan `BEGIN/COMMIT`) sehingga setiap proses yang terpisah dapat memicu state korup apabila interupsi *(crash)* terjadi sebelum commit selesai di kode *handlers*.
