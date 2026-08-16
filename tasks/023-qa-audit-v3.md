# QA Audit V3: Concurrency & Rate Limit Fixes

## Apa yang Dikerjakan
Menjalankan audit menyeluruh (layaknya peran *Senior QA*) pada keseluruhan *codebase* dan mengimplementasikan dua *hotfix* pada celah kerentanan *database* dan limitasi API Telegram.

## Mengapa Dikerjakan
1. **TOCTOU pada Submission Tugas**: Mahasiswa yang menekan tombol kumpul tugas dengan sangat cepat berulang kali (akibat koneksi lambat) berisiko memicu *Race Condition* di `submit_task`. Hal ini sebelumnya akan mengakibatkan `aiosqlite.IntegrityError` (karena *UNIQUE constraint* tabrakan) yang tidak tertangkap, menyebabkan *crash* pada *handler* pengguna tersebut.
2. **Telegram API Flood Wait**: Skrip pengiriman pengumuman absensi harian otomatis (`daily_staff_attendance_open`) mem-*broadcast* pesan ke seluruh staf dengan *looping* tanpa jeda. Jika jumlah staf banyak, hal ini berpotensi terkena blokir sementara (Rate Limit / *Flood Wait*) dari server Telegram.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Perbaikan TOCTOU `submit_task` (`bot/database.py`)**:
   - Pola `INSERT` pada fungsi `submit_task` sekarang dibungkus di dalam blok `try/except`. 
   - Jika terjadi `IntegrityError` saat eksekusi `INSERT` (karena proses paralel dari pengguna yang sama baru saja menyelesaikan *insert* di *thread* async lain), eksekusi akan masuk ke dalam `except Exception:`.
   - Di dalam *exception handler*, bot akan memanggil ulang fungsi itu sendiri secara rekursif (`return await self.submit_task(...)`). Pemanggilan kedua ini akan mendeteksi baris (*row*) yang sudah ada di blok `SELECT`, dan akhirnya memprosesnya menggunakan perintah `UPDATE` yang jauh lebih aman.
2. **Perbaikan Rate Limit Pengumuman (`bot/jobs.py`)**:
   - Di dalam *loop* iterasi perulangan ke seluruh `staff_ids` di dalam fungsi `daily_staff_attendance_open`, telah ditambahkan `await asyncio.sleep(0.05)`. 
   - Jeda 50ms ini memastikan pengiriman mentok pada ~20 pesan per detik, jauh di bawah batas limit Telegram (30 pesan per detik).
