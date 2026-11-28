# Task 176: Penerapan Konsep Akun Kerja (`/link_kerja`) pada `/pfp` & Hardening Anti-Bug

## Latar Belakang & Tujuan
Pada sistem promosi (`/lpm` & `/story`), pengguna sudah dapat menautkan **Akun Kerja** (akun cadangan/klon) ke **Akun Utama** menggunakan `/link_kerja`. Sebelumnya, ketika Akun Kerja digunakan untuk menjalankan `/pfp <link>` (forward postingan channel ke `KEEP_CH_ID`), reward Agra dan log `pfp_logs` tetap masuk ke ID Akun Kerja alih-alih Akun Utama, sehingga saldo Agra terpecah dan rekap `/pfp daily` / `/pfp weekly` menampilkan akun kerja secara terpisah.

Pembaruan ini menerapkan konsep Akun Kerja tersebut secara penuh dan aman pada fitur `/pfp`, sekaligus menutup celah bug penautan/konkurensi agar dapat langsung digunakan oleh pengguna nyata tanpa kendala.

---

## Ringkasan Perubahan Teknis

### 1. Integrasi Akun Kerja di `/pfp` (`bot/handlers/pfp.py`)
- **Resolusi Kredit (`resolve_pfp_credit_user_id`)**:
  - Memetakan `actor_uid` -> `main_user_id` via `db.get_main_account_by_linked(conn, actor_uid)` (memanfaatkan index `idx_linked_accounts_promo`).
  - Memastikan baris `main_user_id` benar-benar ada di tabel `users` (mencegah kegagalan Foreign Key pada `agra_ledger`), melindungi dari kemungkinan siklus/rantai pada data historis, dan tetap aman terhadap fixture/mock pengujian minimal.
- **Atribusi Reward & Log Terpusat (`cmd_pfp`)**:
  - `pfp_logs.user_id` disimpan menggunakan `credit_uid` (`main_user_id`), sehingga `/pfp daily` dan `/pfp weekly` otomatis menggabungkan seluruh kontribusi dari Akun Utama dan seluruh Akun Kerjanya ke satu baris pengguna.
  - `db.add_agra` mengkreditkan poin ke `target_id = credit_uid` dengan `actor_id = uid` serta keterangan eksplisit `Reward forward N post (/pfp via Akun Kerja <uid>)` untuk jejak audit di `/agra log`.
- **Proteksi Konkurensi & Anti-Duplikasi Lintas Akun**:
  - Lock per-user (`_pfp_user_locks()`) dikunci pada `credit_uid` sehingga Akun Utama dan Akun Kerja tidak dapat membalap (*race condition*) satu sama lain saat mem-forward secara bersamaan.
  - Pengecekan duplikasi kloter aktif memeriksa `user_id` pada `credit_uid` (dan `uid` bila via Akun Kerja untuk mencegah klaim ulang post pra-taut), serta menolak pemintaan ulang bagian/subset rentang yang sebelumnya sudah berhasil diforward penuh.
- **Privasi Grup & Isolasi Otoritas**:
  - Jika `/pfp` oleh Akun Kerja dijalankan di **grup**, balasan bot hanya menampilkan `(+N Agra masuk ke Akun Utama tertaut)` tanpa membocorkan ID/username Akun Utama di ruang publik; di private chat (DM), ID Akun Utama ditampilkan jelas.
  - Hak istimewa administratif (`/pfp daily`, `/pfp weekly`, `/post_keep`, `/pfp post`, serta callback `pfp:*`) tetap divalidasi ketat terhadap `uid` pemanggil asli sehingga Akun Kerja tidak pernah mewarisi wewenang Owner/Admin/Divisi PFP.
- **Panduan `/pfp`**:
  - Tutorial `/pfp` kini mencantumkan dukungan Akun Kerja dan menampilkan baris status khusus apabila pengirim sedang menggunakan Akun Kerja yang tertaut.

### 2. Hardening Penautan & Pemutusan Tautan Akun Kerja (`bot/database.py`, `bot/handlers/promo.py`, `bot/handlers/commands.py`)
- **Database (`bot/database.py`)**:
  - Menjaga `add_linked_account` dari tautan ke diri sendiri (`main_user_id == promo_user_id`), menambahkan pengurutan deterministik (`ORDER BY created_at ASC, ... LIMIT 1`) pada `get_main_account_by_linked` dan `get_linked_accounts`, serta menambahkan method `remove_linked_account(conn, main_user_id, promo_user_id)`.
- **Pencegahan Bug Penautan (`bot/handlers/promo.py`)**:
  - **1 Akun Kerja = Maksimal 1 Akun Utama**: Menolak penautan apabila `promo_user_id` sudah tertaut ke Akun Utama lain.
  - **Anti-Rantai & Anti-Siklus**: Menolak `/link_kerja` dari akun yang sudah berstatus Akun Kerja, dan menolak penautan bila pembuat OTP berstatus Akun Kerja atau kandidat Akun Kerja sudah memiliki Akun Kerja sendiri.
  - **Konsumsi OTP Atomik & FK-Safe**: Mengonsumsi OTP secara atomik sebelum `INSERT` ke database, memastikan baris kedua akun ada pada tabel `users` (mencegah error Foreign Key tersembunyi), membersihkan `onboarding_step` tersisa pada Akun Kerja setelah tautan sukses, serta memperketat filter regex OTP hanya pada `ChatType.PRIVATE`.
  - **Manajemen & Pemutusan Tautan Mandiri**: Memperkaya `/cek_akun_kerja` untuk menampilkan nama/username + tombol putuskan tautan interaktif (termasuk tampilan status & tombol putuskan saat dipanggil dari sisi Akun Kerja), serta menambahkan `/unlink_kerja [id|@username]` dan callback `unlink_kerja:` berproteksi IDOR.
- **Panduan `/help` (`bot/handlers/commands.py`)**:
  - Menambahkan ringkasan `/link_kerja / /cek_akun_kerja` pada daftar perintah umum.

---

## Catatan Batasan Teknis
- Integrasi ini mengandalkan mekanisme bot & userbot server (`checker.py`) yang sudah ada: postingan dari channel publik maupun channel privat yang diikuti bot/userbot server dapat langsung diforward oleh Akun Kerja dan otomatis masuk ke Akun Utama. Namun, bot tidak memiliki akses sesi ke akun pribadi pengguna, sehingga channel privat yang hanya diikuti oleh Akun Kerja (dan tidak diikuti bot maupun userbot `checker.py`) tetap tidak dapat dibaca oleh bot.

---

## Verifikasi & Pengujian
- **Pengujian Baru (`tests/test_pfp_akun_kerja.py`)**: Menambahkan 10 skenario terisolasi meliputi alur E2E `/link_kerja` -> OTP -> `/pfp` (single & range) -> `/pfp daily` & `/pfp weekly`, privasi balasan di grup, anti-duplikasi kloter lintas akun (termasuk pra-taut, subset, dan partial-failure retry), lock konkurensi lintas akun, isolasi privilege Owner/Admin/PFP, validasi integritas tautan (anti multi-main, anti siklus/rantai, auto-ensure FK), fallback data historis rusak, `/cek_akun_kerja` + `/unlink_kerja` + proteksi IDOR, pengecekan `EXPLAIN QUERY PLAN` (tanpa *Full Table Scan*), serta registrasi handler.
- **Hasil Pengujian**:
  - `python -m py_compile` pada seluruh berkas terdampak & AST parse 40 file (`bot/`, `main.py`, `checker.py`): **Lulus (0 error)**.
  - `pyrefly check bot/database.py bot/handlers/promo.py bot/handlers/pfp.py bot/handlers/commands.py checker.py main.py`: **0 errors**.
  - Dry-run registrasi `Application` (`setup_jobs` + `setup_handlers`): **Lulus (`11` jobs, group `-1:1, 0:107, 1:4, 2:2`)**.
  - Perbandingan DDL `bot/database.py` vs Turso dev DB (`sqlite_master`): **Missing tables: `[]`, Missing indexes: `[]` (29 tabel, 40 indeks)**.
  - `pytest` (offline suites: `test_pfp_akun_kerja.py`, `test_pfp.py`, `test_pfp_qa.py`, `test_pfp_deep.py`, `test_pfp_poster_qa_deep.py`, `test_post_keep_and_schedules.py`, `test_help_and_export_json.py`, `test_keep_forwarder.py`, `test_qa_all_fixes.py`, `test_messages_chunking.py`): **110 passed**.
  - `pytest` (Turso dev DB: `test_promo_lpm.py`, `test_pindah_data.py`, `test_qa_fixes.py`): **8 passed**.
  - `python tests/test_qa_master_audit.py`: **93 passed, 0 failed**.
