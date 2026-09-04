# Task 053: Full Code Audit Fixes

## Tujuan
Memperbaiki temuan bug dari hasil Full Code Audit untuk memastikan bot lebih stabil dan aman, terutama pada path krusial (seperti onboarding maba dan admin data).

## Pekerjaan yang Dilakukan

1. **Perbaikan Critical Crash Bugs**:
   - Memperbaiki `NameError: name 'ids_set' is not defined` pada `bot/handlers/commands.py` (BUG-C1). Mengganti `ids_set` menjadi `ids` saat proses *toggling* multiple choice admin.
   - Mengganti impor konstan *hardcoded* `MABA_GROUP_LINKS` yang sudah usang di `bot/handlers/messages.py` dengan *dynamic invite link generation* memakai `MABA_GROUP_GIDS` dan `MABA_GROUP_NAMES` agar tidak menyebabkan *Crash/ImportError* (BUG-C2).
   - Menambahkan `import html` di `bot/handlers/menfess.py` untuk mencegah `NameError` saat memanggil `html.escape` (BUG-C3).
   - Menambahkan `import json` dan `can_approve_profile` di `bot/handlers/messages.py` untuk mencegah `NameError` pada saat penebusan kode maba dan fitur edit teks admin (BUG-C4 dan BUG-H4).

2. **Perbaikan High-Severity Bugs**:
   - Memperbaiki SQL injection potential pada `list_active_bot_chats` di `bot/database.py` dengan menggunakan parameterized query daripada *f-string* interpolation (BUG-H1).
   - Membatasi infinite recursion (potensi stack overflow) pada method `submit_task` di `bot/database.py` akibat *retry* pada kondisi *race condition* atau *integrity error* (BUG-H6).

3. **Perbaikan Medium-Severity Bugs**:
   - Memperbaiki *Maba Onboarding Step* yang selalu ter-reset ke `None` pada proses verifikasi grup (`MABA_REASON` flow di `messages.py`), yang menyebabkan maba tidak bisa melanjutkan langkah jika belum memvalidasi channel (BUG-M1).
   - Mengganti semua HTTP call `requests.post()` sinkron menjadi asinkron dengan menggunakan `asyncio.to_thread()` di dalam file `checker.py`, sehingga bot checker tidak lagi mengalami *event loop blocking* ketika menunggu respons Telegram (BUG-M2).
   - Menambahkan *role validation* pada fungsi `/maba` (`cmd_maba`) sehingga hanya publik atau maba yang dapat menggunakannya, untuk mencegah admin atau role internal mengacaukan datanya sendiri (BUG-M7).
   - Menghindari potensi *HTML injection* pada fungsi `format_profile_card` dengan meng-*escape* `full_name` secara eksplisit menggunakan `html.escape(raw)` (BUG-M8).
   - Menyeragamkan `parse_mode` menjadi `HTML` pada flow maba onboarding (sebelumnya campur aduk dengan Markdown) untuk mencegah error pada parsing karakter khusus nama pengguna atau reason maba (BUG-M9, LOGIC-5).
   - Memperbaiki *window limit* pada format `birth_date` agar tahun berawalan `30` (misalnya 2030) tidak disalahpahami sebagai 1930. Batas diubah dari tahun `30` menjadi `50` (1950 - 2049) (BUG-M11).
   - Memastikan eksekusi skema database (SCHEMA) berjalan pada SQLite maupun Turso, dan *re-raise* error `executescript` pada `AiosqliteConnectionMock` alih-alih melewatinya secara diam-diam (BUG-M4, BUG-M5).
   - Menyempurnakan logika *cashback* di `menfess.py` (BUG-M6) menjadi atomik (`add_agra_cashback_if_first_today`) berbasis `agra_ledger` untuk menangani kelemahan *Time-Of-Check to Time-Of-Use* (TOCTOU) dari pengiriman menfess massal simultan.

4. **Perbaikan Security, Logic, dan Performance (Low & Perf)**:
   - Mengimplementasikan `rate_limit_check` di `common.py` (berbasis in-memory) dan mengaplikasikannya ke menu `/menfess` untuk memitigasi potensi *spamming* (SEC-3).
   - Menambahkan filter *Regex Strict* (`^https?://t\.me/`) pada validasi URL promo LPM dan Story untuk mencegah penyisipan parameter atau domain manipulatif (SEC-4).
   - Menambahkan verifikasi *Role Applicability* (`field_applies_to_role`) pada fitur admin *edit profile* di `commands.py` untuk memastikan field relevan dengan target (SEC-5).
   - Merapikan utilitas *Timezone Offset* yang *hardcoded* di `menfess.py` menjadi menggunakan helper `bot.timefmt.get_local_time` secara konsisten (LOGIC-4).
   - Menghapus pembacaan paksa `_auto_close_stale_sessions` dari setiap fungsi baca (*read*) pada sesi kelas presensi, dan mendelegasikannya penuh kepada cron/job (*background*) untuk menghemat beban DB (BUG-L4).
   - Memasukkan mekanisme `in-memory debounce` (`group_activity_cache`) di `messages.py` untuk mengeliminasi >60% penulisan berulang pada `touch_group_seen_user` dan `upsert_bot_chat` untuk user di grup yang sama dalam jangka waktu berdekatan (PERF-3).

## Status
- Masih terdapat temuan arsitektur besar dari hasil audit (misal: single shared DB connection) yang ditunda perbaikannya karena membutuhkan refaktor masif.
- Dokumentasi `tasks/053-full-code-audit-fixes.md` selesai dibuat.
