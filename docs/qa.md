# QA MENDALAM — BOT TELEGRAM DHRU

QA level produksi terhadap **seluruh sistem bot**. Bukan code review — inspeksi, eksekusi, reproduksi, buktikan masalah.

**Aturan:** Jangan modifikasi kode produksi · Jangan percaya audit sebelumnya · Jangan berhenti setelah 1 bug · Jangan klaim PASS tanpa bukti · Kirim pesan hanya ke `TESTER_ID` · Gunakan `tests/` + Turso dev DB, bukan produksi.

## 1. Discovery Sistem
Pahami interaksi antar komponen:

| Komponen | Detail |
|---|---|
| Handlers | `commands.py`, `attendance.py`, `broadcast.py`, `kontrak.py`, `kts.py`, `kic.py`, `tugas.py`, `messages.py`, `triggers.py` |
| FSM/State | ConversationHandler PTB, `context.user_data` |
| Auth/Roles | `owner > admin > internal/bem > student > maba > public` |
| Database | Turso via `libsql_client` — DDL di `bot/database.py` |
| IPC Userbot | `checker.py` ↔ tabel `userbot_requests` |
| Config | `.env`, YAML (`choices.yaml`, `profile_fields.yaml`) |
| Background | scheduler presensi Ospek, broadcast jobs |

## 2. Eksekusi Nyata
Jalankan: `python -m pytest tests/` · Lint (`ruff`/`flake8`) · typecheck (`mypy`) · cek dependensi/keamanan · bandingkan DDL `database.py` vs tabel aktual · jalankan bot jika bisa, periksa log/crash. Yang tidak bisa diuji → **UNVERIFIED** + alasan.

## 3. Tes Fitur End-to-End
Untuk **setiap** fitur, tes alur: **INPUT → HANDLER → VALIDASI → AUTH → STATE → LOGIC → DB → RESPONSE → CLEANUP**

| Kategori | Fitur |
|---|---|
| Akun | `/start`, `/profil`, `/lengkapi`, `/ubah`, `/maba` |
| Akademik | `/presensi` (buka/tutup/hadir/rekap), `/tugas` (upload/kumpul/review) |
| Agra | `/leaderboard`, `/transfer`, `/pay`, `/add` |
| Sosial | `/menfess`, `/menfess_read`, `/link_kerja`, `/cek_akun_kerja` |
| Promo | `/lpm`, `/story`, `/promo` |
| Admin | `/setrole`, `/admin_data`, `/pending`, `/broadcast`, `/trigger` |
| Owner | `/orreset_user`, `/orreset_agra`, `/reload`, `/pull`, `/ospek_mode` |
| Grup | `/kicknot`, `/setgreeting`, `/greeting`, `/fix`, `/export_photos` |
| Kartu | `/kartu`, `/foto` (KTS/KIC) |
| Games | `/bermain`, `/settings_game`, `/atur`, `/ikut`, `/mulai_game`, dll |
| Laporan | `/laporan`, `/daftar`, `/detail` |

**Skenario per fitur (minimal):** Happy path · input kosong/salah tipe/boundary/Unicode-emoji/sangat panjang · duplikat/rapid request/spam · batal/retry/urutan tak terduga · akses tanpa otorisasi (user biasa panggil fitur admin).

## 4. Alur User Realistis
Tes journey multi-langkah: user baru→`/start`→`/lengkapi`→`/profil`→`/presensi` · fitur A→B→C→kembali A · input salah→koreksi→berhasil · batal di tengah→kembali nanti · command saat ConversationHandler aktif · callback basi/resource dihapus · double-click/rapid action. Fokus: **bug dari urutan/interaksi antar fitur.**

## 5. FSM / State / Session
Trace setiap transisi ConversationHandler: entry→transisi→exit→cleanup · batal/timeout/abandon→state bersih · command/callback masuk saat state aktif · data session lama tidak bocor. **Wajib: state User A tidak pernah memengaruhi User B.**

## 6. Multi-User / Konkruensi
Simulasikan: beberapa user simultan di fitur sama · rapid request dari 1 user · CRUD konkuren (contoh: 2 admin buka presensi bersamaan). Cari: race condition, state collision, respons ke user salah, data bocor, duplikasi, lost update, bypass permission.

## 7. Database / Integritas Data
Tes CRUD + kondisi gagal: ID invalid/dihapus · duplikat · DB kosong · modifikasi konkuren · partial failure/rollback. **Konsistensi DB↔Telegram:** DB sukses+reply gagal→tidak boleh konfirmasi palsu · DB gagal+reply sukses→**BUG KRITIS**. Perhatian khusus `agra_ledger` (atomik, saldo valid). Verifikasi isolasi data (IDOR).

## 8. Keamanan / Penyalahgunaan
Bertindak sebagai **attacker**, jangan andalkan UI. Manipulasi: user/chat ID, callback_data, argumen command, urutan request, permission. Tes: bypass auth · IDOR · privilege escalation · callback auth flaw · SQL injection via profil/trigger · kebocoran secret di log · path traversal upload.

## 9. Kegagalan / Recovery
Simulasikan: API error/timeout/FloodWait · DB disconnect · config hilang/salah · exception tak terduga. Setelah gagal verifikasi: **bot hidup + state valid + DB konsisten + retry OK + cleanup selesai + tanpa duplikasi/korupsi/silent failure.**

## 10. Edge Cases & Stabilitas
`None`/0/negatif/max int/string panjang · field hilang/extra di `profile_json` · callback basi/double-click/spam · dataset kosong vs besar · blocking di async · N+1 query · memory/connection/task leak · rate-limit/FloodWait · handler lambat/processing tak terbatas.

## 11. Regresi & Pass Kedua
Jangan modifikasi kode produksi. Bug reprodusibel → buat tes terpisah. Setelah pass pertama, ulangi dari perspektif: user ceroboh/jahat/spammer · admin/owner · user konkuren · kegagalan Telegram/DB/restart. Tanyakan: **"Apa yang masih bisa rusak di penggunaan nyata yang terlewat?"**

## Aturan Bukti

| Status | Arti |
|---|---|
| **PASS** | Dieksekusi dan berhasil |
| **FAIL** | Dieksekusi dan gagal |
| **UNVERIFIED** | Tidak bisa dieksekusi (+ alasan) |

Jangan mengarang hasil. Setiap bug: ID · Severity (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) · file+line · root cause · reproduksi · aktual vs ekspektasi · dampak · bukti · rekomendasi.

## Laporan Akhir
```
# LAPORAN QA BOT
## STATUS: Overall (PASS/PASS WITH ISSUES/FAIL/UNVERIFIED) · Production Ready (YES/NO/UNVERIFIED)
## MATRIKS FITUR
| Fitur | Happy Path | Edge Case | Error | Security | Konkruensi | E2E | Final |
## EKSEKUSI TES
| Tes | Command/Metode | Hasil | Bukti |
## BUG (severity tertinggi duluan)
## KEAMANAN
## STATE/FSM
## DATABASE
## TELEGRAM
## PERFORMA/STABILITAS
## UNVERIFIED (+ alasan)
## CELAH TES
## TOP 10 RISIKO
## VONIS AKHIR
Semua fitur berfungsi · alur user OK · DB konsisten · multi-user aman · FSM aman · permission aman · recovery OK · bot stabil · keamanan memadai · layak produksi
```

**Jangan berhenti di inspeksi. Jangan berhenti setelah menemukan bug. Tes sedalam mungkin. MULAI SEKARANG.**
