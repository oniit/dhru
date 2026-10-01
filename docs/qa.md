# QA MENDALAM — BOT TELEGRAM DHRU

Lakukan **QA level produksi** terhadap **seluruh sistem bot** sebagai satu kesatuan.

**Ini BUKAN code review. Tugasmu: inspeksi, eksekusi, reproduksi, dan buktikan masalah.**

## Aturan Utama
- **JANGAN** modifikasi kode produksi.
- **JANGAN** percaya audit/tes sebelumnya.
- **JANGAN** berhenti setelah menemukan bug.
- **JANGAN** klaim PASS tanpa benar-benar diuji.
- **JANGAN** kirim pesan ke user nyata — hanya ke `TESTER_ID`.
- Gunakan test suite di folder `tests/` dengan Turso DB khusus developing di environment, **bukan** DB produksi Turso.

---

## 1. DISCOVERY SISTEM

Pelajari keseluruhan sistem — pahami interaksi antar komponen, bukan fungsi terisolasi:

- **Handlers**: `commands.py`, `attendance.py`, `broadcast.py`, `kontrak.py`, `kts.py`, `kic.py`, `tugas.py`, `messages.py`, `triggers.py`
- **FSM/State**: ConversationHandler PTB, `context.user_data`
- **Auth/Roles**: `owner > admin > internal/bem > student > maba > public`
- **Database**: Turso (remote) via `libsql_client` — DDL di `bot/database.py`
- **IPC Userbot**: `checker.py` ↔ tabel `userbot_requests`
- **Config**: `.env` (credentials), YAML (`choices.yaml`, `profile_fields.yaml`)
- **Background**: scheduler presensi Ospek, broadcast jobs

---

## 2. EKSEKUSI NYATA

Jalankan semua yang tersedia:

- `python -m pytest tests/` (menjalankan seluruh test suite di folder `tests/`)
- Lint (`ruff`/`flake8`), typecheck (`mypy`)
- Cek dependensi/keamanan
- Cek skema DB (bandingkan DDL di `database.py` vs tabel aktual)
- Jika environment memungkinkan: jalankan bot, periksa log/exception/crash

Area yang tidak bisa diuji karena keterbatasan environment → tandai **UNVERIFIED**, lanjutkan sisanya.

---

## 3. TES FITUR END-TO-END

Untuk **SETIAP** fitur, tes alur lengkap:

**USER → TELEGRAM → HANDLER → VALIDASI → AUTH → STATE → LOGIC → DB → RESPONSE → CLEANUP**

### Fitur yang Harus Diuji

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

### Skenario Per Fitur (minimal)
- Happy path
- Input kosong / salah tipe / boundary / Unicode-emoji / sangat panjang
- Duplikat / rapid request / spam
- Batal / retry / urutan tak terduga
- Akses tanpa otorisasi (coba akses admin dari user biasa)

---

## 4. ALUR USER REALISTIS

Tes journey multi-langkah:

- User baru → `/start` → `/lengkapi` → `/profil` → `/presensi`
- Fitur A → B → C → kembali ke A
- Input salah → koreksi → berhasil
- Batal di tengah → kembali nanti
- Kirim command saat ConversationHandler lain aktif
- Callback basi / resource sudah dihapus
- Double-click / rapid action

Fokus: **bug yang muncul karena urutan atau interaksi antar fitur.**

---

## 5. FSM / STATE / SESSION

Trace setiap state & transisi ConversationHandler:

- Entry → transisi → exit → cleanup
- Batal / timeout / abandon → state harus bersih
- Command/callback masuk saat state aktif
- Data session lama tidak bocor

**Wajib verifikasi: data/state USER A tidak pernah memengaruhi USER B.**

---

## 6. MULTI-USER / KONKRUENSI

Simulasikan:
- Beberapa user simultan di fitur yang sama
- Rapid request dari user yang sama
- CRUD konkuren pada resource yang sama (contoh: 2 admin buka presensi bersamaan)

Cari: race condition, state collision, respons ke user salah, data bocor, duplikasi operasi, lost update, bypass permission.

---

## 7. DATABASE / INTEGRITAS DATA

Tes setiap jalur CRUD + kondisi gagal:

- ID tidak ada / sudah dihapus / invalid
- Duplikat entry
- DB kosong
- Modifikasi konkuren
- Partial failure / rollback

**Konsistensi DB ↔ Telegram:**
- DB sukses tapi reply Telegram gagal → user tidak boleh dapat konfirmasi palsu
- DB gagal tapi Telegram sudah reply sukses → **ini bug kritis**

Perhatian khusus pada `agra_ledger`: transaksi atomik, saldo tidak boleh negatif secara tidak sah.

Verifikasi isolasi data antar user (IDOR).

---

## 8. KEAMANAN / PENYALAHGUNAAN

Bertindak sebagai **attacker**. Jangan andalkan batasan UI.

Manipulasi: user/chat ID, callback_data, argumen command, urutan request, permission.

Tes:
- Bypass auth/admin (contoh: user biasa panggil `/broadcast`)
- IDOR (akses data user lain via ID)
- Privilege escalation (`student` → `admin`)
- Callback authorization flaw
- Injection (SQL via input profil/trigger)
- Kebocoran secret/token di log/error
- Path traversal di upload file

---

## 9. KEGAGALAN / RECOVERY

Simulasikan kegagalan yang feasible:

- Telegram API error / timeout / FloodWait
- DB disconnect / timeout (Turso)
- Konfigurasi hilang / salah
- Exception tak terduga

Setelah kegagalan, verifikasi:
**Bot hidup + state valid + DB konsisten + retry berfungsi + cleanup selesai + tidak ada duplikasi/korupsi/silent failure.**

---

## 10. EDGE CASES & STABILITAS

- `None`, 0, negatif, max int, string sangat panjang
- Field hilang / extra di `profile_json`
- Callback basi, double-click, spam
- Dataset kosong vs sangat besar
- Blocking operation di async code
- N+1 query / query berlebihan
- Memory/connection/task leak
- Rate-limit / FloodWait risk
- Handler lambat / processing tak terbatas

---

## 11. REGRESI & PASS KEDUA

**JANGAN** modifikasi kode produksi.

Bug yang bisa direproduksi → buat tes reproduksi terpisah (non-produksi).

Setelah pass pertama, ulangi dari perspektif:
- User ceroboh / user jahat / spammer
- Admin / owner
- User konkuren
- Kegagalan Telegram / DB / restart proses

Tanyakan: **"Apa yang masih bisa rusak di penggunaan nyata yang terlewat?"**

---

## ATURAN BUKTI

| Status | Arti |
|---|---|
| **PASS** | Benar-benar dieksekusi dan berhasil |
| **FAIL** | Benar-benar dieksekusi dan gagal |
| **UNVERIFIED** | Tidak bisa dieksekusi (sebutkan alasan) |

**Jangan pernah mengarang hasil tes.**

Setiap bug yang dikonfirmasi harus memuat:
- ID, Severity (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW`)
- Lokasi (file + line), Root cause
- Cara reproduksi, Perilaku aktual vs ekspektasi
- Dampak, Bukti, Rekomendasi perbaikan

---

# LAPORAN AKHIR

```
# LAPORAN QA BOT

## STATUS SISTEM
- Overall: PASS / PASS WITH ISSUES / FAIL / UNVERIFIED
- Production Ready: YES / NO / UNVERIFIED

## MATRIKS FITUR
| Fitur | Happy Path | Edge Case | Error | Security | Konkruensi | E2E | Final |

## EKSEKUSI TES
| Tes | Command/Metode | Hasil | Bukti |

## BUG (severity tertinggi duluan)
## KEAMANAN
## STATE/FSM
## DATABASE
## TELEGRAM (command/callback/message)
## PERFORMA/STABILITAS
## UNVERIFIED (beserta alasan)
## CELAH TES (coverage otomatis yang hilang)

## TOP 10 RISIKO

## VONIS AKHIR
Nyatakan secara eksplisit apakah:
- Semua fitur berfungsi
- Alur user utama bekerja
- DB konsisten
- Multi-user aman
- FSM/state aman
- Permission aman
- Recovery berfungsi
- Bot stabil
- Keamanan memadai
- Layak produksi
```

**Jangan berhenti di inspeksi. Jangan berhenti setelah menemukan bug. Tes sedalam mungkin.**

MULAI SEKARANG.
