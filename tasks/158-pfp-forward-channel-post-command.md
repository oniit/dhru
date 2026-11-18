# Task 158: Fitur Perintah /pfp (Channel Post Forwarder & Owner Statistics)

## 1. Latar Belakang & Tujuan
Menambahkan fitur baru bernama `/pfp` yang memungkinkan seluruh pengguna (baik di obrolan pribadi/DM maupun grup) untuk mem-forward postingan dari channel Telegram (baik channel publik maupun privat) ke channel penyimpanan (`KEEP_CH_ID`). Perintah ini mendukung forwarding 1 postingan tunggal maupun rentang banyak postingan sekaligus (`/pfp <link_awal> to <link_akhir>`).

Selain itu, jika perintah `/pfp` dikirimkan tanpa argumen, bot menampilkan panduan interaktif cara penggunaan. Khusus untuk Owner (`OWNER_ID`), bot menyediakan sub-menu eksklusif:
- **PFP Daily:** Menampilkan daftar pengguna yang berhasil mem-forward postingan hari ini beserta jumlah postingan yang mereka forward.
- **PFP Weekly:** Menampilkan ringkasan ringkas statistik forward harian selama 7 hari terakhir (jumlah pengguna unik dan total postingan per hari).

## 2. Rincian Perubahan & Implementasi Teknis

### A. Parser Tautan & Argumen (`bot/handlers/pfp.py`)
- `parse_telegram_post_link(link: str)`:
  - Membersihkan karakter pembungkus seperti `<...>`, `(...)`, `[...]`, `"` atau `'`.
  - Memisahkan query string (seperti `?single`) dan garis miring penutup (`/`).
  - Mengenali format publik (`t.me/<username>/<msg_id>`) dan privat (`t.me/c/<channel_num>/<msg_id>`).
  - Mengonversi format privat ke ID bot internal (`-100<channel_num>`).
- `parse_pfp_args(args: list[str])`:
  - Mendeteksi argumen kosong -> `TUTOR`.
  - Mendeteksi sub-command `daily` atau `weekly`.
  - Memisahkan rentang dengan regex `\s+to\s+` (case-insensitive) -> `RANGE`.
  - Mendeteksi single link -> `SINGLE`.

### B. Mekanisme Forwarding Multi-Layer
1. **Direct Bot API (Fast Path):**
   - Menggunakan `bot.forward_messages(...)` untuk batch forward hingga 100 pesan sekaligus.
   - Jika terdapat pesan yang terhapus di dalam rentang batch, fallback ke iterasi pesan individual menggunakan `bot.forward_message(...)` dengan jeda 0.15 detik untuk menghindari rate limit Telegram.
2. **Userbot Fallback (IPC via `checker.py`):**
   - Jika Bot API gagal akibat kendala perizinan channel privat (`ChatNotFound` atau `Forbidden`), bot mengajukan permohonan ke tabel `userbot_requests` dengan action `FORWARD:<from_chat>:<start_id>:<end_id>`.
   - Script `checker.py` memproses permohonan tersebut secara paralel menggunakan Pyrogram dan mengembalikan jumlah pesan yang berhasil diforward.

### C. Basis Data & Optimasi Kuota Turso (`bot/database.py`)
- Dibuat tabel baru `pfp_logs`:
  - Kolom: `id`, `user_id`, `chat_id`, `channel_id`, `first_msg_id`, `last_msg_id`, `forwarded_count`, `created_at`.
  - Dilengkapi index: `idx_pfp_logs_created_at` pada `created_at` dan `idx_pfp_logs_user_date` pada `(user_id, created_at)`.
- Mengimplementasikan method:
  - `log_pfp_forward(...)`: Mencatat forward yang berhasil.
  - `get_pfp_daily_stats(...)`: Mengambil agregasi pengguna dan jumlah post hari ini (WIB) menggunakan `LEFT JOIN users` dan `SUM(forwarded_count)`.
  - `get_pfp_weekly_stats(...)`: Mengambil log 7 hari terakhir dengan index scan waktu.
- Penambahan `pfp_logs` ke rutinitas migrasi otomatis dan fungsi pembersihan `reset_all_data_except_users`.

### D. Sub-Menu & Antarmuka Interaktif Owner
- Tombol inline:
  - `[ 📊 PFP Daily ]` (callback `pfp:daily`)
  - `[ 📅 PFP Weekly ]` (callback `pfp:weekly`)
  - `[ 🔄 Refresh ]` & `[ 🔙 Panduan /pfp ]` (callback `pfp:menu`)
- Callback handler `cb_pfp` memvalidasi `is_owner(uid)`; pengguna non-owner yang menekan tombol akan menerima notifikasi toast `show_alert=True`.

### E. Integrasi & Registrasi Handler
- `bot/handlers/register.py`: Menambahkan `CommandHandler("pfp", pfp.cmd_pfp)` dan `CallbackQueryHandler(pfp.cb_pfp, pattern="^pfp:")`.
- `bot/handlers/commands.py`: Menambahkan perintah `/pfp` pada panduan `/help` (perintah umum) dan `/help_owner` (menu Owner).

## 3. Pengujian & Quality Assurance (QA)
- Menuliskan unit & integration test terpusat di `tests/test_pfp.py` dan `tests/test_pfp_qa.py` mencakup 28 skenario pengujian komprehensif:
  - **Happy Path:**
    - Forward single post (channel publik & privat).
    - Forward rentang post dengan pemisah `to` dan `-`.
    - Tampilan tutorial `/pfp` reguler vs menu bertombol untuk Owner.
    - Rekap statistik harian (`pfp daily`) dan mingguan (`pfp weekly`).
  - **Edge Cases & Proteksi Input:**
    - Parsing URL dengan query string, fragment (`#`), trailing slash, dan tanda kurung/kutip (`<...>`, `"..."`, `[...]`).
    - Penanganan otomatis pembalikan rentang (`link/20 to link/10`).
    - Validasi batas maksimal 100 post (100 diizinkan, 101 ditolak).
    - Validasi kesamaan channel sumber pada forward rentang.
    - Budgeting dan pemotongan daftar panjang pengguna pada PFP Daily (maksimal 3300 karakter untuk mencegah error Telegram 4096 karakter).
    - Penanganan gracefully saat database belum terhubung (NoneType guard).
  - **Keamanan & Otorisasi:**
    - Non-owner diblokir saat memanggil `/pfp daily` maupun `/pfp weekly`.
    - Non-owner diblokir saat menekan tombol callback `pfp:daily`, `pfp:weekly`, dan `pfp:menu` (alert toast).
    - Owner memiliki akses penuh ke perintah dan callback navigasi.
  - **Resiliensi & Error Handling:**
    - Penanganan hilangnya konfigurasi `KEEP_CH_ID`.
    - Fallback pesan individual jika batch forward Telegram Bot API gagal karena post terhapus.
    - Fallback IPC ke userbot (`checker.py`) jika Bot API tidak memiliki izin di channel privat.
    - Tangkapan aman `BadRequest: Message is not modified` saat tombol refresh ditekan berulang kali.
    - Pembersihan tabel `pfp_logs` saat eksekusi `reset_all_data_except_users`.
- Seluruh 28 pengujian berhasil lulus 100% tanpa kendala (`28 passed in 1.73s`).
