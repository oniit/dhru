# Task 132: Optimasi Efisiensi Read Turso Database & Eliminasi Full Table Scan

## Ringkasan Masalah
Pengguna melaporkan bahwa database produksi Turso (`bot`) mencapai **504.699.782 baris dibaca (*rows read*)** meskipun ukuran database hanya **1.25 MB** dan total baris tertulis (*rows written*) hanya **40.701**. Hal ini memicu pemblokiran akun Turso secara otomatis karena melebihi kuota bulanan free-tier (500 juta rows read/bulan).

Setelah dilakukan audit kode secara menyeluruh (*holistic debugging*), ditemukan akar penyebab teknis:
1. **Ketiadaan Index pada Kolom Filter & Status Antrean**:
   - Polling berkala di `checker.py` mengeksekusi kueri `SELECT * FROM promo_verifications WHERE status = 'PENDING'` dan `SELECT * FROM userbot_requests WHERE status = 'PENDING'` setiap 2 detik.
   - Job queue di `bot/jobs.py` mengeksekusi `SELECT * FROM broadcast_jobs WHERE status = 'pending'`, `SELECT * FROM promo_verifications WHERE status = 'PENDING'`, dan auto-close presensi setiap 10–60 detik.
   - Kolom-kolom antrean ini (`status`, `closed_at`, `opened_at`, `username`) sebelumnya **tidak memiliki INDEX**. Akibatnya, mesin basis data SQLite/libSQL melakukan **Full Table Scan** (menyisir seluruh baris tabel dari awal hingga akhir) pada setiap eksekusi kueri, meskipun antrean kosong (*pending count = 0*).
   - Dengan 43.200 kali kueri per hari, kueri unindexed ini menimbun puluhan juta pembacaan baris setiap harinya hingga tembus 500 juta dalam hitungan hari.
2. **Frekuensi Polling Statis Tanpa Backoff**:
   - Loop `checker.py` mengeksekusi pengecekan setiap 2.0 detik secara kaku bahkan ketika tidak ada antrean atau aktivitas pengguna yang sedang diproses.

---

## Solusi & Perbaikan yang Diterapkan

### 1. Penambahan 19 Index Terdedikasi pada Skema DDL ([`bot/database.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/database.py))
Menambahkan indeks pada kolom-kolom kritis yang sering difilter (`WHERE`, antrean, relasi foreign key, dan fungsi case-insensitive):
- `idx_users_username_lower`: Index fungsional `lower(username)` pada tabel `users`.
- `idx_group_seen_username_lower`: Index fungsional `lower(username)` pada `group_seen_users`.
- `idx_group_seen_chat_bot`: Index komposit `(chat_id, is_bot, last_seen_at)`.
- `idx_promo_status`: Index `promo_verifications(status)`.
- `idx_promo_link`: Index `promo_verifications(link)`.
- `idx_promo_user_status`: Index komposit `promo_verifications(user_id, status)`.
- `idx_userbot_requests_status`: Index `userbot_requests(status)` untuk IPC userbot.
- `idx_broadcast_jobs_status`: Index komposit `broadcast_jobs(status, id)`.
- `idx_attendance_sessions_class_closed`: Index `attendance_sessions(class_id, closed_at)`.
- `idx_attendance_sessions_closed_opened`: Index `attendance_sessions(closed_at, opened_at)`.
- `idx_attendance_sessions_opened_by`: Index `attendance_sessions(opened_by)`.
- `idx_attendance_records_user`: Index `attendance_records(telegram_id)`.
- `idx_task_open`: Index `task_assignments(is_open, created_at)`.
- `idx_game_sessions_active`: Index `game_sessions(chat_id, is_active)`.
- `idx_audit_log_actor`: Index `audit_log(actor_id)`.
- `idx_linked_accounts_promo`: Index `linked_accounts(promo_user_id)`.
- `idx_bot_chats_active_type`: Index `bot_chats(is_active, type)`.
- `idx_charyarthi_q_div_order`: Index `charyarthi_questions(division_id, question_order)`.
- `idx_agra_actor`: Index `agra_ledger(actor_telegram_id)`.

**Verifikasi `EXPLAIN QUERY PLAN`**:
Seluruh kueri antrean telah diverifikasi langsung terhadap database Turso dan terbukti berubah dari `SCAN TABLE` menjadi `SEARCH ... USING INDEX` (dan `USING COVERING INDEX`). Saat antrean kosong, pembacaan baris tabel menjadi **0 rows read**.

### 2. Adaptive Polling Delay pada Worker ([`checker.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/checker.py))
- Memodifikasi `process_userbot_requests` untuk mengembalikan jumlah item yang diproses (`len(pending_rows)`).
- Menghitung jumlah antrean aktif pada setiap iterasi:
  - **Kondisi Aktif** (`pending_count > 0` atau `userbot_count > 0`): Jeda dipercepat menjadi `1.0 detik` agar antrean diproses instan dan responsif.
  - **Kondisi Idle** (tidak ada antrean): Jeda dinaikkan menjadi `3.5 detik` untuk menghemat frekuensi request jaringan dan beban komputasi Turso, namun tetap sangat responsif terhadap batas waktu IPC (5–10 detik).

### 3. Pembaruan Aturan AI & Dokumentasi
- Menambahkan aturan wajib baru pada [`.agents/AGENTS.md`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/.agents/AGENTS.md): **"Aturan: Efisiensi Pembacaan Database & Perlindungan Kuota Turso (Read Optimization)"**, memastikan AI selalu memprioritaskan efisiensi pembacaan data, keberadaan index, in-memory cache, dan adaptive backoff sebelum mengimplementasikan fitur atau kueri baru.
- Memperbarui [`docs/database.md`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/docs/database.md) pada bab Efisiensi Pembacaan & Optimasi Index.

---

## Verifikasi & QA
1. **Query Plan Verification**:
   - `SELECT * FROM promo_verifications WHERE status = 'PENDING'` -> `SEARCH promo_verifications USING INDEX idx_promo_status (status=?)`
   - `SELECT * FROM userbot_requests WHERE status = 'PENDING'` -> `SEARCH userbot_requests USING INDEX idx_userbot_requests_status (status=?)`
   - `SELECT * FROM broadcast_jobs WHERE status = 'pending' ORDER BY id ASC LIMIT 1` -> `SEARCH broadcast_jobs USING INDEX idx_broadcast_jobs_status (status=?)`
   - `SELECT telegram_id, first_name, username FROM group_seen_users WHERE lower(username) = ? LIMIT 1` -> `SEARCH group_seen_users USING INDEX idx_group_seen_username_lower (<expr>=?)`
   - `SELECT id FROM attendance_sessions WHERE closed_at IS NULL AND opened_at < ?` -> `SEARCH attendance_sessions USING COVERING INDEX idx_attendance_sessions_closed_opened (closed_at=? AND opened_at<?)`
2. **Regression Testing**:
   - `test_chat_command.py`: 3 passed in 20.42s (100%).
   - `test_promo_lpm.py`: 5 passed in 24.63s (100%).
   Logika seluruh fitur bot tetap utuh tanpa ada perubahan fungsi (*behavior preserved*).

