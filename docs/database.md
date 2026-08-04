# Database Schema & Data Dictionary

Bot menggunakan SQLite. Skema database diinisialisasi melalui fungsi `init_db()` di `bot/database.py`.

## Tabel Utama

### 1. `users`
Menyimpan data otentikasi utama dan profil JSON _schema-less_.
- `telegram_id` (INTEGER PRIMARY KEY)
- `username`, `first_name`, `last_name` (Terkait telegram)
- `language_code`, `is_premium`, `is_bot`
- `role` (TEXT): Peran pengguna (`owner`, `admin`, `internal`, `bem`, `student`, `public`).
- `profile_json` (TEXT): Objek JSON fleksibel menyimpan jawaban formulir (NIM, fakultas, jurusan, TTL, dll).
- `agra_total` (INTEGER): Saldo Agra saat ini.

### 2. `bot_chats`
Menyimpan daftar grup tempat bot ditambahkan. Berguna untuk `/broadcast`.
- `chat_id` (INTEGER PRIMARY KEY)
- `chat_type` (TEXT)
- `title` (TEXT)
- `is_active` (INTEGER)

### 3. `audit_logs`
Sistem pencatatan terpusat untuk segala kejadian penting (Transfer Agra, persetujuan admin, dll).
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `telegram_id` (INTEGER)
- `action` (TEXT)
- `details` (TEXT)
- `created_at` (REAL)

### 4. `profile_change_requests`
Menampung permintaan dari user biasa yang mengubah _field_ sensitif (dikunci). Admin menggunakan `/pending` untuk memutus (`ACC`/`Tolak`).
- `id` (INTEGER)
- `telegram_id` (INTEGER)
- `proposed_json` (TEXT)
- `status` (TEXT): `pending`, `accepted`, `rejected`.

### 5. `agra_history`
Riwayat keluar-masuk (mutasi) poin Agra.
- `id` (INTEGER PRIMARY KEY)
- `target_id` (INTEGER): Penerima/Pemilik
- `actor_id` (INTEGER): Siapa yang memberi (Bot/Dosen/Orang lain)
- `amount` (INTEGER): Minus berarti pemotongan.
- `description` (TEXT)

### 6. `attendance_sessions` & `attendance_records`
Manajemen sesi absen yang dibuka dosen, serta entri absen mahasiswanya.

### 7. `tasks` & `task_submissions`
Manajemen tugas dosen dan tempat berkumpulnya kiriman jawaban (_submission_) mahasiswa.

### 8. `triggers`
Tabel untuk `/trigger`. Menyimpan `keyword` dan daftar balasan (`actions_json`).

### 9. `menfess_history`
Menyimpan riwayat pengiriman pesan rahasia (menfess) antar pengguna beserta gift Agra.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `sender_id` (INTEGER): Pengirim menfess
- `receiver_id` (INTEGER): Penerima menfess
- `message_text` (TEXT): Isi pesan
- `gift_agra` (INTEGER): Jumlah Agra yang diberikan
- `created_at` (REAL): Waktu pengiriman

## Migrasi ke Turso (Database Edge/Remote)
Secara default, bot menggunakan SQLite lokal (`data/bot.db`). Namun bot mendukung database Turso melalui *environment variables*: `TURSO_DB_URL` dan `TURSO_AUTH_TOKEN`.
Jika Anda memiliki data di SQLite lokal dan ingin memindahkannya ke Turso, Anda dapat menggunakan skrip migrasi yang telah disediakan:
```bash
python migrate_vps_to_turso.py
```
Skrip ini akan mengambil semua tabel dari `data/bot.db` dan melakukan *insert/replace* secara otomatis ke database Turso Anda yang diatur di `.env`.
