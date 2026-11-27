# Task 174: Fix Keep-to-Poster Session Lock (`database is locked`), `process_broadcast_queue` Error & PFP QA Bugs

## Akar Masalah Live VPS (Log & Analisis)

Dari pemeriksaan proses VPS dan log `journalctl -u botdhru`, ditemukan dua akar masalah di produksi:

1. **False Failure `"Gagal mem-forward pesan"` meski post sudah masuk `@DhruvaPoster`:**
   - Pada VPS, `checker.py` dan `main.py` berjalan paralel sebagai dua proses terpisah, sementara `.env` mengisi `KEEP_CH_ID` dan `POST_CH_ID` **tanpa** `USERBOT_SESSION`.
   - Sebelumnya `execute_keep_to_post` di `bot/jobs.py` langsung membuka `Client("checker", ...)` pada file SQLite `checker.session` yang sedang dikunci oleh `checker.py` (serta memakai `no_updates=True`).
   - Ketika `app.forward_messages(...)` dipanggil, Pyrofork berhasil mengirim `messages.ForwardMessages` ke server Telegram (sehingga postingan benar-benar terkirim ke `@DhruvaPoster`), lalu di internal `invoke()` memanggil `self.fetch_peers()` yang mencoba menulis ke SQLite `checker.session` dan melempar `sqlite3.OperationalError: database is locked`.
   - Error pasca-kirim tersebut memicu fallback per-pesan (yang ikut gagal dengan error yang sama), membuat `forwarded_count` tetap `0`, pesan di `KEEP_CH_ID` gagal terhapus, dan bot melaporkan `"Gagal! Seluruh pesan tidak dapat di-forward."` padahal pesan sudah masuk `@DhruvaPoster`.

2. **Error Berulang Tiap 10 Detik pada `process_broadcast_queue` (`bot/jobs.py`):**
   - Impor lokal `import asyncio` di dalam badan `process_broadcast_queue` membayangi (*shadowing*) modul global `asyncio`, memicu `UnboundLocalError: cannot access local variable 'asyncio' where it is not associated with a value` saat `broadcast_lock` diinisialisasi.

---

## Ringkasan Perbaikan Teknis

### 1. Delegasi IPC `KEEP_TO_POST` (Mencegah Konflik `checker.session`)
- **`bot/jobs.py`**:
  - Mengekstrak logika scan/forward/delete ke helper bersama `run_keep_forward_with_client(app, keep_ch_id, post_ch_id, bot_id=None, last_fwd_id=0)`.
  - Menambahkan `_try_keep_to_post_via_ipc(...)`: bila `USERBOT_SESSION` kosong, `execute_keep_to_post` mengirimkan request `KEEP_TO_POST:<last_fwd_id>:<bot_id>` ke tabel `userbot_requests`, menunggu klaim `checker.py` (8 detik) hingga selesai (120 detik), lalu tetap menjalankan fallback hapus Bot API (`bot.delete_messages`) terhadap `undeleted_ids` di `main.py`.
  - Menghapus `no_updates=True` dari inisialisasi Pyrogram fallback dan menambahkan pesan diagnostik yang jelas apabila file `checker.session` masih terkunci karena `checker.py` belum di-restart.
- **`checker.py`**:
  - Memuat `POST_CH_ID` dari environment, menambahkan klaim atomik (`PENDING -> PROCESSING` dengan `updated_at`), memperpanjang kedaluwarsa request `FORWARD:` dan `KEEP_TO_POST` menjadi `120` detik (`30` detik untuk aksi lain), dan menangani aksi `KEEP_TO_POST` dengan memanggil `bot.jobs.run_keep_forward_with_client`.

### 2. Perbaikan `UnboundLocalError` di `bot/jobs.py`
- Memindahkan impor `json` ke tingkat modul dan menghapus seluruh impor lokal yang membayangi (`import asyncio`, `import json`, `import html`) pada `process_broadcast_queue`, `daily_staff_attendance_open`, `daily_birthday_reminder`, dan `daily_maba_attendance_open`.

### 3. Perbaikan Bug QA `/pfp` & Keep-to-Poster (`BUG-01` s.d. `BUG-10`)
- **`BUG-01` (`bot/handlers/pfp.py`)**: `parse_telegram_post_link` menggunakan `re.fullmatch`, mendukung tautan topik forum (`t.me/c/<chat_id>/<topic_id>/<msg_id>` -> mengambil `msg_id`), dan menolak trailing karakter acak (`/12abc`). `parse_pfp_args` memisahkan `link1-link2` tanpa spasi dan menolak multi-tautan tanpa kata kunci `to` sebagai `INVALID`.
- **`BUG-02` (`bot/handlers/pfp.py`)**: Menambahkan self-loop guard (`KEEP_CH_ID`, `POST_CH_ID`, `@DhruvaPoster`), per-user lock berbasis `WeakKeyDictionary` (`_pfp_user_locks()`), serta pengecekan duplikasi tautan identik pada `pfp_logs` dalam kloter berjalan.
- **`BUG-03` (`bot/jobs.py`)**: `safe_last_fwd_id` dibatasi ketat `< min(failed_ids)` sehingga pesan di tengah batch yang gagal sementara tidak terlewati permanen pada kloter berikutnya.
- **`BUG-04` (`bot/handlers/pfp.py`)**: Menambahkan flag `agra_added`; apabila `add_agra` gagal (misal karena FK belum `/start`), bot menampilkan catatan peringatan alih-alih mengklaim `(+N Agra)` secara keliru.
- **`BUG-05` (`bot/database.py`, `bot/handlers/pfp.py`)**: `create_userbot_request` langsung mengeksekusi `await conn.commit()`, `_forward_via_userbot_ipc` membaca row via `_row_val` (aman untuk `sqlite3.Row`/`AiosqliteRowMock`/`dict`) dengan timeout dinamis `25..90s`.
- **`BUG-06` (`bot/jobs.py`)**: Eksekusi kloter otomatis (`is_manual=False`) menunggu pelepasan `keep_forward_lock` hingga `120s` via `asyncio.wait_for` alih-alih gagal seketika bila `/post_keep` sedang berjalan.
- **`BUG-08` (`bot/handlers/pfp.py`)**: Menangani `telegram.error.RetryAfter` pada fallback per-pesan `forward_posts_to_keep` dengan tidur sesuai `retry_after` dan mencoba ulang 1 kali.
- **`BUG-09` (`bot/jobs.py`)**: Mempersempit pola pengecualian di `is_keep_msg_excluded` dari `"cek @dhruvaposter"` menjadi `"cek @dhruvaposter,"` agar postingan promosi biasa tidak ikut tersaring.
- **`BUG-10` (`bot/database.py`)**: Menambahkan migrasi `UPDATE pfp_logs SET user_id = ? WHERE user_id = ?` pada `migrate_user_data` (`/pindah_data`).

---

## Pengujian & Verifikasi
- Memperbarui dan menambah pengujian di [`tests/test_pfp_poster_qa_deep.py`](../tests/test_pfp_poster_qa_deep.py) untuk seluruh regresi `BUG-01`..`BUG-10`, alur delegasi IPC `KEEP_TO_POST` + fallback `bot.delete_messages`, serta `process_broadcast_queue`.
- Pemeriksaan kompilasi (`py_compile`), tipe (`pyrefly check bot/handlers/pfp.py bot/jobs.py checker.py bot/database.py`), dan unit test (`pytest` across `test_post_keep_and_schedules.py`, `test_pfp_poster_qa_deep.py`, `test_keep_forwarder.py`, `test_pfp.py`, `test_pfp_deep.py`, `test_pfp_qa.py`, `test_help_and_export_json.py`):
  - **Hasil**: `87 passed in 62.68s`, `pyrefly` `0 errors`.

## Catatan Deployment VPS
Karena perbaikan komunikasi IPC `KEEP_TO_POST` mengubah kedua sisi (`bot/jobs.py` di `main.py` dan `checker.py`), pembaruan di VPS setelah `/pull` wajib diikuti:
1. Restart bot utama (`/reload`).
2. Restart proses `checker.py` di VPS agar handler `KEEP_TO_POST` aktif (atau opsional: set `USERBOT_SESSION` terpisah di `.env`).
