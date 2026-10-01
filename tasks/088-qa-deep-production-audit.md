# 088 — QA Mendalam Level Produksi (Oktober 2026)

## Apa yang Dikerjakan

Melakukan QA mendalam (deep audit) terhadap seluruh sistem bot Telegram Dhru sesuai
panduan di `docs/qa.md`. Audit mencakup:

1. **Eksekusi Tes Otomatis** — Menjalankan semua test suite (`test_logic.py`,
   `test_presensi.py`, `test_major_logic.py`, `test_presensi_ukm.py`) dengan pytest.
2. **Static Analysis** — Menjalankan `ruff check` pada seluruh modul `bot/`.
3. **Code Review Keamanan** — Memeriksa semua handler untuk auth bypass, IDOR,
   SQL injection, privilege escalation, dan shell command execution.
4. **Analisis FSM/State** — Memeriksa `onboarding_step`, `context.user_data`,
   ConversationHandler, dan potensi state leakage.
5. **Database Integrity** — Memeriksa atomicity, race conditions, dan constraint handling.
6. **Analisis Concurrency** — Meninjau shared connection, locking, dan atomic operations.

## Temuan Utama

- **13 bug teridentifikasi**: 2 CRITICAL, 3 HIGH, 5 MEDIUM, 3 LOW
- **Test results**: 3 PASS, 1 FAIL (missing `@pytest.mark.asyncio`)
- **Ruff lint**: 1979 error (mostly styling/line length)
- **Security**: `/reload` dan `/pull` terlalu permisif (admin bisa, seharusnya owner saja)
- **Database**: Agra transfer tidak atomik di Turso (potensi double-spend)

## Alur Teknis

1. Tes dijalankan dengan `python -m pytest` — menginstal `pytest-asyncio` karena belum tersedia.
2. `ruff check bot/ --select E,F,W` menunjukkan 1979 error, sebagian besar styling.
3. Setiap handler command diperiksa untuk pola auth: `row["role"]`, `is_owner()`,
   `can_manage_agra()`, `can_approve_profile()`, dll.
4. `deduct_agra_if_sufficient()` menggunakan `INSERT...SELECT WHERE SUM >= amount`
   untuk atomicity — aman di SQLite lokal, tapi `AiosqliteConnectionMock.commit()`
   adalah no-op sehingga multi-step operations tidak dijamin atomik di Turso.
5. `os.system("sudo systemctl restart botdhru")` di `/reload` adalah blocking shell
   call yang bisa diakses admin (bukan hanya owner).

## File yang Diperiksa

- `bot/database.py` — Schema DDL, semua method CRUD, agra ledger, attendance
- `bot/handlers/commands.py` — 4758 baris, semua 43 command handler
- `bot/handlers/common.py` — Permission functions, profile formatting
- `bot/handlers/attendance.py` — Presensi open/close/hadir/izin
- `bot/handlers/broadcast.py` — Broadcast to users
- `bot/handlers/triggers.py` — Auto-reply system
- `bot/handlers/menfess.py` — Anonymous message system
- `bot/handlers/messages.py` — Private message FSM, onboarding state machine
- `bot/handlers/register.py` — Handler registration
- `bot/settings.py` — Configuration loading
- `bot/jobs.py` — Scheduled tasks
- `main.py` — Application entry point
- `config/choices.yaml`, `config/profile_fields.yaml`, `config/rewards.yaml`
- Semua test files

## Laporan Lengkap

Laporan QA lengkap tersedia di artifact `qa_report.md`.
