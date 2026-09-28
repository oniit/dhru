# 087 — Perbaikan Bug Sistem & Pembersihan DB Lokal (Turso Exclusive)

## Ringkasan Perubahan

Sesi ini menyelesaikan perbaikan 8 bug yang teridentifikasi dalam Audit QA serta melakukan pembersihan penuh terhadap seluruh konfigurasi database SQLite lokal, memastikan sistem secara eksklusif menggunakan database Turso baik untuk *production* maupun *developing/testing*.

---

## Rincian Perbaikan Bug & Modifikasi

### 1. BUG-04 & Keamanan Parsing ID (`bot/settings.py`)
- **Masalah**: `_parse_id_list` menggunakan `part.isdigit()` yang menolak ID integer negatif (seperti ID grup Telegram).
- **Perbaikan**: Mengganti `part.isdigit()` dengan blok `try...except ValueError` setelah `int(part)`.
- **Keamanan**: Perbaikan ini menjamin ID positif, ID negatif grup Telegram, dan variasi format diparse dengan aman tanpa resiko *exception* atau bug lanjutan.

### 2. BUG-01 — TOCTOU Menfess (`bot/handlers/menfess.py`)
- **Masalah**: Ada pemeriksaan saldo non-atomik `agra_total < total_deduct` sebelum transaksi deduction.
- **Perbaikan**: Dihapus agar `deduct_agra_if_sufficient` (atomic deduction subquery) menjadi satu-satunya *single source of truth*.

### 3. BUG-02 — Error Handling PRAGMA & Migrasi (`bot/database.py`)
- **Masalah**: `PRAGMA table_info` dan `ALTER TABLE` dapat memicu kegagalan startup pada koneksi Turso / HTTP libSQL client.
- **Perbaikan**: Setiap migrasi kolom `ALTER TABLE` di-wrap dalam blok `try...except Exception` bertingkat, menjamin bot dapat melakukan startup secara aman di lingkungan SQLite maupun Turso.

### 4. BUG-03 — Relaiabilitas Rowcount Turso Mock (`bot/database.py`)
- **Masalah**: `AiosqliteCursorMock` dapat mengembalikan `rowcount = 0` pada query `INSERT INTO ... SELECT ... WHERE` meskipun baris berhasil disisipkan.
- **Perbaikan**: 
  - `AiosqliteCursorMock.__init__` mengecek `lastrowid` untuk menset `affected = 1` bila row baru berhasil dibuat.
  - `deduct_agra_if_sufficient` memeriksa `(cur.rowcount > 0) or (cur.lastrowid > 0)`.

### 5. BUG-05 — Pytest & Suite Pengujian Async (`test_logic.py`, `test_presensi.py`, `test_major_logic.py`)
- **Masalah**: Pengujian async tidak memiliki dekorator `@pytest.mark.asyncio`. Selain itu skrip tes lama mencoba menghapus / menggunakan file SQLite lokal `test_logic_88.sqlite3`.
- **Perbaikan**:
  - Semua file tes ditambahkan `@pytest.mark.asyncio` dan dipadukan dengan runner pytest.
  - Menghapus logika penciptaan SQLite lokal (`test_logic_88.sqlite3`, `test_presensi.sqlite3`).
  - Pengujian mengandalkan koneksi `Database()` yang membaca `TURSO_DB_URL` & `TURSO_AUTH_TOKEN` dari environment dev.

### 6. BUG-06 — Missing Import `os` di `bot/jobs.py`
- **Perbaikan**: Menambahkan `import os` di top-level `bot/jobs.py`.

### 7. BUG-07 — Pembaruan Dokumentasi Schema (`docs/database.md`)
- **Perbaikan**: Memperbaiki nama tabel (misal `audit_log`), menambahkan tabel baru (`access_codes`, `game_settings`, `game_sessions`, `group_seen_users`), serta membersihkan byte terkorupsi pada tabel `broadcast_jobs`.

### 8. BUG-08 — Eksolusi Session Auto-Close (`bot/database.py`)
- **Perbaikan**: Mengubah query `_auto_close_stale_sessions` menjadi `WHERE class_id NOT IN ('staff_auto', 'maba_auto')`.

---

## Pembersihan Lingkungan & Dokumentasi

1. **Penghapusan File Lokal**: File `test_logic_88.sqlite3` dan `test_presensi.sqlite3` telah dihapus.
2. **Pembaruan Dokumen**:
   - `docs/database.md`: Menjelaskan Turso DB sebagai pilihan eksklusif untuk dev & prod.
   - `docs/architecture.md`: Memperbarui Tech Stack Database menjadi Turso DB (`libsql_client`).
   - `.agents/AGENTS.md`: Menyelaraskan aturan pengujian QA dengan Turso dev DB.
