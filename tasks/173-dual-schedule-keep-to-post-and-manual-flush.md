# Task 173: Dual-Schedule Keep-to-Post Forwarding, Manual Flush & Owner Kloter Report

## Ringkasan Perubahan
Memperbarui sistem pengiriman postingan dari channel penyimpanan (`KEEP_CH_ID`) ke channel poster publik (`POST_CH_ID` / `@DhruvaPoster`):
1. **Penambahan Kloter Otomatis Baru**: Menjadwalkan 2 kloter harian otomatis di Telegram JobQueue:
   - Kloter 1: Jam **15:00 WIB**
   - Kloter 2: Jam **17:59 WIB**
2. **Laporan Kloter ke Private Chat Owner (`/pfp` vs Forwarded)**:
   - Setiap eksekusi kloter (15:00 WIB & 17:59 WIB, serta `/post_keep` yang dijalankan oleh admin/staf non-owner), sistem mengirimkan ringkasan ke private chat Owner (`OWNER_ID`) apabila ada aktivitas forward atau perintah `/pfp` pada rentang kloter tersebut:
     - Jumlah perintah `/pfp` yang berhasil dan total post masuk KEEP dari `/pfp`.
     - Jumlah post aktual yang terforward ke `@DhruvaPoster` dan yang terhapus dari KEEP.
     - Selisih keduanya (sebagai pegangan Owner apabila ada post di KEEP yang dihapus manual).
3. **Command Manual untuk Postingan Terlambat/Susulan**:
   - Menambahkan perintah `/post_keep` (beserta alias `/pfp_post`, `/flush_keep`, dan sub-command `/pfp post`).
   - Menyediakan tombol pintas `🚀 Post Manual (/post_keep)` di menu tutorial Owner/Staff `/pfp`.
   - Hak akses dibatasi untuk Owner, Admin, atau Staf Internal Divisi PFP (`d_pfp` / `pfp`).
4. **Pembersihan Atomik Pesan di KEEP (Anti-Repost)**:
   - Setiap kali pesan berhasil diforward ke poster (baik melalui jadwal otomatis maupun manual), pesan-pesan tersebut langsung dihapus dari `KEEP_CH_ID` menggunakan `app.delete_messages` dengan fallback Bot API `bot.delete_messages`.
   - Tetap memperbarui `keep_last_fwd_id` di database Turso sebagai proteksi redundan sekunder.
5. **Proteksi Konkurensi (Concurrency Lock)**:
   - Menambahkan `asyncio.Lock` (`get_keep_forward_lock()`) berbasis `weakref.WeakKeyDictionary` pada `execute_keep_to_post` agar jadwal otomatis dan perintah manual tidak saling tabrakan atau memicu konflik sesi Pyrogram.

---

## Alur Teknis & Implementasi

1. **`bot/database.py`**:
   - Menambahkan `get_pfp_kloter_stats(conn, start_ts, end_ts)`: Mengagregasi `COUNT(id)` dan `COALESCE(SUM(forwarded_count), 0)` dari `pfp_logs` menggunakan index `idx_pfp_logs_created_at` (`WHERE created_at > ? AND created_at <= ?`) agar hemat kuota reads Turso.

2. **`bot/jobs.py`**:
   - `get_keep_forward_lock()`: Menginisialisasi `asyncio.Lock` per event loop aktif via `weakref.WeakKeyDictionary`.
   - `_resolve_owner_chat_id(conn)` & `_format_keep_kloter_owner_report(...)`: Menyusun dan mengirim ringkasan perbandingan `/pfp` berhasil vs post terforward ke private chat Owner.
   - `execute_keep_to_post(bot, db=None, conn=None, is_manual=False, kloter_label=None, triggered_by=None)`:
     - Memeriksa konfigurasi, mengakuisisi lock, menjalankan Pyrogram client (`USERBOT_SESSION` atau fallback `checker`).
     - Mengambil pesan baru (`> keep_last_fwd_id` & tidak excluded), mem-forward dalam batch/chunk 100 dengan fallback per pesan, lalu menghapus pesan yang berhasil diforward (`app.delete_messages` -> fallback `bot.delete_messages`).
     - Mengagregasi `get_pfp_kloter_stats` sejak `keep_last_report_ts` (default awal: 00:00 WIB hari berjalan), memperbarui `keep_last_report_ts`, dan mengirim laporan kloter ke private chat Owner (termasuk kasus ketika semua post `/pfp` dihapus manual sehingga 0 post terforward).
   - `daily_keep_to_post(context)`: Wrapper JobQueue yang meneruskan `kloter_label` (`15:00 WIB` / `17:59 WIB`).
   - `setup_jobs(application)`: Mendaftarkan `keep_to_post_1500` (15:00 WIB) dan `keep_to_post_1759` (17:59 WIB) dengan `data={"kloter_label": ...}`.

3. **`bot/handlers/pfp.py`**:
   - `parse_pfp_args`: Menambahkan deteksi sub-command `POST` (`post`, `flush`, `kirim`, `forward`, `manual`).
   - `is_authorized_pfp_admin`: Memvalidasi hak akses Owner, Admin (`sqlite3.Row` & `dict`), atau Staf Internal Divisi PFP (`position_detail` berisi `d_pfp`/`pfp` atau `position == 'pfp'` via `profile_from_row` & `get_user_jabatans`).
   - `cmd_post_keep`, `cmd_pfp`, `cb_pfp`, `get_pfp_tutorial_text`: Integrasi perintah manual, sub-command `/pfp post`, serta tombol inline `pfp:post`.

4. **`bot/handlers/register.py` & `bot/handlers/commands.py`**:
   - Mendaftarkan `["post_keep", "pfp_post", "flush_keep"]` dan memperbarui panduan `/help` serta `/help_owner`.

---

## Pengujian & Verifikasi
- Pengujian unit baru di `tests/test_post_keep_and_schedules.py` (20 test cases):
  - `test_parse_pfp_args_post_subcommands`
  - `test_setup_jobs_schedules_1500_and_1759`
  - `test_is_authorized_pfp_admin`
  - `test_cmd_post_keep_unauthorized` & `test_cmd_post_keep_success`
  - `test_cmd_pfp_subcommand_post`
  - `test_execute_keep_to_post_forwards_and_deletes`
  - `test_execute_keep_to_post_delete_fallback_to_bot_api`
  - `test_database_get_pfp_kloter_stats`
  - `test_daily_keep_to_post_notifies_owner_kloter_stats`
  - `test_daily_keep_to_post_all_deleted_manually_still_notifies_owner`
  - `test_daily_keep_to_post_empty_kloter_no_spam`
  - `test_execute_keep_to_post_concurrency_lock`
  - `test_cb_pfp_post_button`
  - `test_is_keep_msg_excluded_includes_all_fail_notice`
  - `test_execute_keep_to_post_breaks_at_last_fwd_id`
  - `test_execute_keep_to_post_delete_fallback_when_pts_count_zero`
  - `test_execute_keep_to_post_retries_single_on_floodwait`
  - `test_daily_keep_to_post_notifies_owner_on_error`
  - `test_pfp_tutor_and_help_for_pfp_staff`
- Audit perbaikan tambahan pasca-review (`bot/jobs.py`, `bot/handlers/pfp.py`, `bot/handlers/commands.py`, `bot/handlers/common.py`):
  - Pengecualian pesan error `"Seluruh pesan tidak dapat di-forward"` di `is_keep_msg_excluded` agar tidak ikut ter-forward pada kloter berikutnya.
  - Penghentian iterasi `get_chat_history` dengan `break` saat menyentuh `last_fwd_id` serta pemakaian `no_updates=True` pada `Client`.
  - Pengambilan `scan_end_ts` tepat setelah scan history agar `/pfp` yang masuk saat chunk forwarding berlangsung tidak salah tercatat sebagai selisih kloter berjalan.
  - Fallback hapus ke Bot API apabila `app.delete_messages` mengembalikan `0` (`pts_count == 0`), retry 1x untuk `FloodWait` di fallback single-message, serta notifikasi DM ke Owner bila job kloter otomatis gagal.
  - Ekstraksi helper `is_pfp_division_profile` di `common.py` dan `_format_manual_post_result` di `pfp.py`, penyediaan tombol `🚀 Post Manual (/post_keep)` untuk Divisi PFP/Admin di `/pfp`, serta visibilitas `/post_keep` di `/help` khusus staf PFP.
- Rangkaian pengujian regresi (`test_post_keep_and_schedules.py`, `test_keep_forwarder.py`, `test_pfp.py`, `test_pfp_deep.py`, `test_pfp_qa.py`, `test_help_and_export_json.py`):
  - **Hasil**: 65 passed in 19.43s tanpa error setelah perbaikan audit terakhir.
