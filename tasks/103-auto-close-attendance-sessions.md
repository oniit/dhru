# 103 - Auto Close Attendance Sessions

## Ringkasan Masalah
Pada sesi presensi manual yang dibuka melalui `/presensi buka` (kelas akademik, BEM, UKM, event bebas), sesi presensi sebelumnya tidak pernah ditutup secara otomatis jika opener/admin lupa mengetik `/presensi tutup <id_sesi>`. Akibatnya:
1. Sesi presensi tetap menggantung (berstatus aktif) berhari-hari bahkan berminggu-minggu di database.
2. Ketika admin atau opener ingin membuka sesi baru untuk kelas yang sama, sistem menolak dengan pesan error: `⚠️ Sesi presensi untuk ... sudah dibuka sebelumnya (ID: ...). Tutup sesi tersebut terlebih dahulu dengan /presensi tutup <id> sebelum membuka sesi baru.`

Fungsi `_auto_close_stale_sessions` sebenarnya sudah pernah dibuat di `bot/database.py` (dengan cutoff 7200 detik / 2 jam), namun pemanggilannya sebelumnya dicopot saat audit performa (Task 053) dan belum pernah didaftarkan ke scheduler / background job queue.

## Solusi & Implementasi
1. **Pembaruan Database (`bot/database.py`)**:
   - Memperbarui fungsi `auto_close_stale_sessions(conn, timeout_seconds=7200)` agar mengembalikan daftar ID sesi yang ditutup (`list[int]`).
   - Query menutup semua sesi manual aktif yang dibuka lebih dari 2 jam lalu (`opened_at < cutoff` dan `class_id NOT IN ('staff_auto', 'maba_auto')`).
   - Sesi di-update dengan `closed_at = opened_at + timeout_seconds`.
   - Tetap mempertahankan `_auto_close_stale_sessions` sebagai alias backward-compatible.

2. **Pendaftaran Background Job & Pembaruan Pesan (`bot/jobs.py`)**:
   - Menambahkan fungsi asynchronous `periodic_auto_close_attendance(context)` yang memanggil `db.auto_close_stale_sessions(conn)`.
   - Untuk setiap sesi yang ditutup otomatis, fungsi memanggil `refresh_presensi_announcement(context, db, conn, sid)` sehingga pesan pengumuman awal di Telegram otomatis diedit: teks berubah menjadi "Ditutup: ..." dan "Sesi ditutup", serta tombol inline (Hadir & Izin) otomatis dihapus (`reply_markup=None`).
   - Menambahkan parameter eksplisit `parse_mode="HTML"` pada seluruh pemanggilan `edit_message_text` di `bot/handlers/attendance.py` agar pemformatan font (seperti **tebal** `<b>`, miring `<i>`, dan monospace `<code>`) dirender dengan sempurna oleh Telegram alih-alih menampilkan raw tag HTML.
   - Mendaftarkan job tersebut ke `job_queue` menggunakan `jq.run_repeating(periodic_auto_close_attendance, interval=60, first=15)` sehingga secara periodik (setiap 60 detik) sistem memeriksa dan menutup sesi presensi yang telah melewati batas 2 jam (atau sesuai env `PRESENSI_AUTOCLOSE_TIMEOUT`).

3. **Pengujian Otomatis (`tests/test_auto_close_presensi.py`)**:
   - Menambahkan suite pengujian terisolasi untuk memastikan:
     - Sesi manual yang usianya > 2 jam ditutup otomatis dan nilai `closed_at` dihitung tepat.
     - Sesi `staff_auto` (presensi harian) tidak ikut tertutup karena memiliki cron penutup tersendiri pukul 23:59 WIB.
     - Sesi yang baru dibuka (< 2 jam) tetap terbuka (aktif).
     - Job queue memanggil `edit_message_text` dengan `reply_markup=None` (tombol terhapus) dan teks "Sesi ditutup."
   - Pengujian 100% lulus (2 passed in 16.58s).

4. **Pembaruan Dokumentasi**:
   - Memperbarui `docs/architecture.md` (bagian Proteksi Keamanan & Integritas State).
   - Memperbarui `docs/commands.md` (keterangan perintah `/presensi`).
