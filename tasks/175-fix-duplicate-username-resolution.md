# Task 175: Fix Duplicate Username Resolution & Stale Username Self-Healing (Opsi C)

## Akar Masalah
Saat pengguna memanggil perintah berbasis `@mention` seperti `/add 3969 @siiqal penyesuaian`, bot mengkreditkan Agra (dan mencetak dua penerima) ke dua akun berbeda (`Skylia Iqalla` dan `iqalla`). Hal ini disebabkan oleh dua celah yang saling berkaitan:
1. **Stale Username di Sumber (`users` & `group_seen_users`)**: Skema `users.username` tidak memiliki constraint unik. Saat pengguna memindahkan `@username` dari akun lama ke akun baru dan akun lama tidak pernah mengirim pesan lagi ke bot, `upsert_user_from_telegram`, `sync_user_basic_info`, dan `touch_group_seen_user` hanya meng-update baris `telegram_id` aktif tanpa membersihkan `username` usang pada baris `telegram_id` lain.
2. **Lookup Konsumer Tanpa Disambiguasi**:
   - `Database.find_ids_by_usernames` mengambil **semua** `telegram_id` yang cocok (`SELECT telegram_id FROM users WHERE lower(username) IN (...)`), sehingga `cmd_add`, `cmd_transfer`, dan `cmd_setrole` mengeksekusi aksi ke seluruh akun duplikat.
   - `Database.get_user_by_username_or_id`, `resolve_target_user`, dan `cmd_kick` tidak mengurutkan berdasarkan aktivitas terbaru (`updated_at DESC` / `last_seen_at DESC`) dan tidak mendisambiguasi konflik bila lebih dari satu `telegram_id` memiliki `@username` yang sama.

## Perubahan Teknis

### 1. Pembersihan & Self-Healing di Sumber ([`bot/database.py`](../bot/database.py))
- Menambahkan helper `_clear_stale_username(...)` yang mengosongkan kolom `username = NULL` pada `users` dan/atau `group_seen_users` untuk `lower(username) = ? AND telegram_id != ?` (memanfaatkan index `idx_users_username_lower` dan `idx_group_seen_username_lower` tanpa full table scan).
- Mengintegrasikan `_clear_stale_username` ke:
  - `upsert_user_from_telegram` (saat `/start`).
  - `sync_user_basic_info` (via `global_profile_tracker`, termasuk self-healing saat pertama kali cache kosong setelah restart maupun untuk user yang belum pernah `/start`).
  - `touch_group_seen_user` (membersihkan stale username di `group_seen_users`).
  - `migrate_user_data` (`/pindah_data`).

### 2. Disambiguasi di Konsumer & IPC ([`bot/database.py`](../bot/database.py), [`bot/handlers/common.py`](../bot/handlers/common.py), [`bot/handlers/commands.py`](../bot/handlers/commands.py), [`checker.py`](../checker.py))
- Menambahkan `Database.resolve_usernames_via_ipc(...)` untuk mengirim aksi `RESOLVE:` ke tabel `userbot_requests`.
- Memperbarui `Database.find_ids_by_usernames`:
  - Mengurutkan kandidat `ORDER BY updated_at DESC, created_at DESC, telegram_id DESC`.
  - Jika hanya ada 0–1 baris per username (kasus normal), langsung mengembalikan hasil tanpa memanggil IPC.
  - Jika ada >1 baris untuk username yang sama, melakukan disambiguasi via `resolve_usernames_via_ipc`, membersihkan baris usang (`_clear_stale_username`), dan mengembalikan maksimal **1 ID** per `@username` (dengan fallback ke `updated_at` terbaru bila IPC gagal/timeout).
- Memperbarui `Database.get_user_by_username_or_id`:
  - Menggunakan `ORDER BY updated_at DESC, created_at DESC, telegram_id DESC LIMIT 2`.
  - Bila ditemukan konflik (>1 baris), mendisambiguasi via IPC dan membersihkan baris usang.
- Memperbarui `resolve_target_user` (`bot/handlers/common.py`) dan `cmd_kick` (`bot/handlers/commands.py`):
  - Menghilangkan query duplikat ke `users`, mengurutkan lookup `group_seen_users` per `telegram_id` berdasarkan `MAX(last_seen_at) DESC`, mendisambiguasi konflik via IPC + membersihkan data usang, serta men-guard input `"@"` kosong.
  - Menambahkan guard `if is_target_lookup and not row:` di `cmd_profile`.
- Memperkuat handler `RESOLVE:` di `checker.py` agar fallback per-username saat batch `app.get_users(usernames)` gagal pada salah satu username, serta mendukung `u.usernames` (collectible username).

## Verifikasi
- Pengujian otomatis pada [`tests/test_username_dedup_and_resolution.py`](../tests/test_username_dedup_and_resolution.py) serta regresi terkait (`test_chat_command.py`, `test_pindah_data.py`, `test_presensi_strict_and_kick.py`, `test_pfp_poster_qa_deep.py`).
