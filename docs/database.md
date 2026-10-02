# Database Schema & Data Dictionary

Sistem menggunakan **Turso** (remote database via `libsql_client`) secara eksklusif untuk lingkungan produksi (*production*) maupun pengujian/pengembangan (*developing/testing*). Database SQLite lokal (`data/bot.db`) tidak digunakan dan telah dihapus.

Inisialisasi skema dilakukan melalui string `SCHEMA` dan migrasi otomatis pada method `connect()` di [`bot/database.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/database.py).

---

## Tabel Utama & Struktur Data

### 1. `users`
Menyimpan data akun utama dan profil JSON *schema-less*.
- `telegram_id` (INTEGER PRIMARY KEY): ID pengguna Telegram
- `username`, `first_name`, `last_name` (TEXT): Informasi profil Telegram
- `language_code` (TEXT), `is_premium` (INTEGER), `is_bot` (INTEGER)
- `role` (TEXT NOT NULL DEFAULT 'public'): Peran pengguna (`owner`, `admin`, `internal`, `bem`, `student`, `maba`, `public`)
- `profile_json` (TEXT NOT NULL DEFAULT '{}'): JSON menyimpan data formulir (NIM, fakultas, jurusan, dll)
- `raw_profile_json` (TEXT), `onboarding_step` (TEXT): State onboarding per-user
- `created_at` (REAL), `updated_at` (REAL): Timestamp pembuatan/pembaruan

### 2. `profile_change_requests` & `profile_request_mod_messages`
Menampung pengajuan perubahan profil sensitif oleh user yang memerlukan persetujuan admin/owner.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `telegram_id` (INTEGER NOT NULL): ID Pemohon
- `proposed_json` (TEXT NOT NULL): Perubahan yang diajukan
- `status` (TEXT NOT NULL DEFAULT 'pending'): Status (`pending`, `accepted`, `rejected`)
- `created_at` (REAL), `decided_at` (REAL), `decided_by` (INTEGER)
- `moderator_prompt_text` (TEXT)

### 3. `agra_ledger`
Riwayat mutasi poin Agra (ledger-based). Saldo dihitung dinamis via `SUM(amount)`.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `target_telegram_id` (INTEGER NOT NULL): ID Penerima/Pemilik Agra
- `actor_telegram_id` (INTEGER NOT NULL): ID Pelaku mutasi (Bot/User/Admin)
- `amount` (INTEGER NOT NULL): Jumlah mutasi (positif = penambahan, negatif = pemotongan)
- `description` (TEXT NOT NULL): Alasan/keterangan mutasi
- `chat_id` (INTEGER), `message_id` (INTEGER): Konteks pesan/grup
- `created_at` (REAL NOT NULL)
- **Note**: Pemotongan saldo dilakukan secara atomik (*INSERT INTO ... SELECT ... WHERE*) untuk mencegah *race condition* (TOCTOU).

### 4. `attendance_sessions` & `attendance_records`
Manajemen sesi presensi dan entri kehadiran pengguna.
- `attendance_sessions`: `id`, `class_id`, `title`, `opened_by`, `chat_id`, `opened_at`, `closed_at`, `announce_message_id`, `extra_data`
- `attendance_records`: `id`, `session_id`, `telegram_id`, `recorded_at`, `status` (default: 'hadir')
- **Constraint**: `UNIQUE(session_id, telegram_id)` mencegah presensi ganda.

### 5. `audit_log`
Catatan aktivitas dan audit internal sistem.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `actor_id` (INTEGER): ID Pelaku aksi
- `action` (TEXT NOT NULL): Jenis tindakan
- `detail` (TEXT): Detail keterangan
- `created_at` (REAL NOT NULL)

### 6. `access_codes`
Kode akses pendaftaran/elevasi peran.
- `code` (TEXT PRIMARY KEY)
- `created_at` (REAL NOT NULL), `used_by` (INTEGER), `used_at` (REAL)
- `target_role` (TEXT NOT NULL DEFAULT 'student')

### 7. `triggers`
Keyword triggers otomatis untuk merespons pesan tertentu di obrolan/grup.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `keyword` (TEXT NOT NULL), `actions_json` (TEXT NOT NULL), `created_by` (INTEGER NOT NULL)

### 8. `bot_chats`
Daftar grup tempat bot terpasang.
- `chat_id` (INTEGER PRIMARY KEY), `type` (TEXT), `title` (TEXT), `is_active` (INTEGER DEFAULT 1)
- `greeting_message` (TEXT): Pesan sambutan member baru
- `updated_at` (REAL)

### 9. `task_assignments` & `task_submissions`
Manajemen penugasan dan pengumpulan jawaban tugas.
- `task_assignments`: `id`, `class_id`, `title`, `created_by`, `created_at`, `is_open`
- `task_submissions`: `id`, `task_id`, `student_id`, `content`, `status`, `reject_reason`, `channel_message_id`, `reviewed_by`, `submitted_at`, `reviewed_at`
- **Constraint**: `UNIQUE(task_id, student_id)` mencegah submit ganda.

### 10. `group_seen_users`
Pelacakan anggota grup yang pernah terlihat oleh bot.
- `chat_id` (INTEGER NOT NULL), `telegram_id` (INTEGER NOT NULL), `username` (TEXT), `first_name` (TEXT), `last_name` (TEXT), `is_bot` (INTEGER), `last_seen_at` (REAL)
- `PRIMARY KEY (chat_id, telegram_id)`

### 11. `game_settings`, `game_sessions`, & `group_game_permissions`
Manajemen mini-game obrolan (Kata Rahasia, Tahan Dulu, dll).
- `game_settings`: `id`, `game_name`, `setting_name`, `data_json`
- `game_sessions`: `id`, `chat_id`, `game_name`, `setting_name`, `is_active`, `state_json`, `created_at`, `updated_at`
- `group_game_permissions`: `chat_id`, `game_name`, `is_allowed` (1/0)

### 12. `menfess_history`
Riwayat pengiriman pesan rahasia (menfess) dan Agra gift.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `sender_id` (INTEGER NOT NULL), `receiver_id` (INTEGER NOT NULL)
- `message_text` (TEXT NOT NULL), `gift_agra` (INTEGER DEFAULT 0)
- `created_at` (REAL NOT NULL)

### 13. `promo_verifications` & `linked_accounts`
Verifikasi promosi (LPM / Story) dan akun kerja/klon.
- `promo_verifications`: `id`, `user_id`, `link`, `status`, `promo_type`, `created_at`
- `linked_accounts`: `main_user_id`, `promo_user_id`, `created_at`

### 14. `bot_settings`
Konfigurasi dinamis bot (*key-value*).
- `setting_key` (TEXT PRIMARY KEY), `setting_value` (TEXT NOT NULL)

### 15. `userbot_requests`
Komunikasi antarmuka (IPC) antara `main.py` dan `checker.py` (Pyrogram userbot).
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `chat_id` (TEXT NOT NULL), `action` (TEXT NOT NULL), `status` (TEXT NOT NULL DEFAULT 'PENDING'), `result` (TEXT), `created_at` (REAL), `updated_at` (REAL)

### 16. `user_chat_stats`
Statistik aktivitas pesan pengguna di grup.
- `user_id` (INTEGER NOT NULL), `chat_id` (INTEGER NOT NULL), `message_count` (INTEGER NOT NULL DEFAULT 0), `last_active_at` (REAL NOT NULL)
- `PRIMARY KEY (user_id, chat_id)`

### 17. `broadcast_jobs`
Antrean tugas pengiriman pesan massal (/broadcast).
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `message_text` (TEXT NOT NULL): Isi pesan broadcast
- `target_users_json` (TEXT NOT NULL): JSON array target Telegram ID
- `processed_users_json` (TEXT NOT NULL DEFAULT '[]'): Target yang telah diproses
- `reporter_id` (INTEGER): Telegram ID pemohon broadcast
- `status` (TEXT DEFAULT 'pending'): Status pekerjaan (`pending`, `completed`, `failed`)

### 18. `manosraya_history`
Riwayat pengiriman aspirasi (Yaksa Open Arms).
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `sender_id` (INTEGER NOT NULL): Pengirim pesan
- `message_text` (TEXT NOT NULL): Isi pesan
- `created_at` (REAL NOT NULL)

---

## Konfigurasi Database Turso

Bot ini berjalan eksklusif menggunakan Turso via `libsql_client`. Environment variable berikut wajib tersedia di `.env`:
```env
TURSO_DB_URL=libsql://<your-database>.turso.io
TURSO_AUTH_TOKEN=<your-turso-auth-token>
```
Tidak ada database SQLite lokal yang digunakan untuk testing atau produksi. Seluruh pengujian otomatis dan pengembangan menggunakan credentials Turso pengembangan dari `.env`.