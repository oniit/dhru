# Task 117: Zero-Bug Release Audit & Regression Stabilization

## Latar Belakang & Kebutuhan
Repositori bot memiliki akumulasi perubahan yang signifikan dari Task 095 hingga Task 116 (+3.072 baris, -833 baris pada 21 file kode aktif). Mengingat bot sudah digunakan oleh ribuan pengguna aktif di lingkungan *production*, pengembang membutuhkan jaminan penuh (*zero-bug guarantee*) bahwa pembaruan besar ini tidak merusak (*regress*) alur-alur yang sebelumnya sudah berjalan normal, tidak memicu *crash*, dan dapat di-deploy secara aman tanpa risiko bagi data pengguna.

---

## Langkah-Langkah Eksekusi Audit 5 Lapis (Safety Nets)

### 1. Isolasi Cabang Rilis (*Safety Branch*)
- Membuat dan berpindah ke cabang terisolasi `release-audit` (`git checkout -b release-audit`).
- Memastikan cabang utama `main` tetap bersih dan utuh sebagai titik pemulihan instan (*fail-safe restore point*) jika sewaktu-waktu dibutuhkan.

### 2. Audit Garis Merah (*Red-Line Diff Audit*)
- Menjalankan inspeksi khusus terhadap baris-baris kode yang dihapus atau ditimpa di seluruh file terdampak (`bot/handlers/`, `bot/database.py`, `bot/jobs.py`, `bot/settings.py`).
- Memverifikasi bahwa penghapusan kode lama murni merupakan refaktorisasi ke fungsi *helper* yang lebih aman (seperti perbaikan logika `#balas` di `messages.py`, refaktorisasi `_get_contract_status` di `kontrak.py`, dan pencegahan duplikasi link pada `promo.py`).

### 3. Analisis Statis AST & Verifikasi Nama Variabel (*Scope Analyzer*)
- Memindai seluruh 34 file Python menggunakan pustaka bawaan `ast` (*Abstract Syntax Tree*):
  - Memastikan 0 *syntax error* dan 0 *indentation error*.
  - Memeriksa pemanggilan nama variabel (*Load Context*) terhadap *scope* lokal, parameter, fungsi pembungkus, *globals*, dan *builtins* untuk mencegah potensi `UnboundLocalError` atau `NameError`.
  - Seluruh variabel terverifikasi terdefinisi secara aman.

### 4. Pengujian Regresi Lengkap (*Full Regression Test Suite*)
- Menjalankan 20 skrip pengujian unit dan integrasi otomatis di direktori `tests/` menggunakan `pytest`:
  - Alur pendaftaran maba, charyarthi, dan purva.
  - Alur pembagian kelompok maba dan pemilihan jurusan/fakultas berantai.
  - Alur kartu KTS/KIC dan export foto massal.
  - Alur presensi kelas umum, UKM, dan penutupan otomatis (*auto-close stale sessions*).
  - Alur sistem kontrak kerja dan perpanjangan (*renewal*).
  - Alur verifikasi instan tautan LPM dan story.
  - Alur transfer, ledger Agra, dan leaderboard.
  - Alur otorisasi role, scope dekan, dan filter perintah `/all`.
- **Hasil:** Seluruh pengujian (39 kasus uji) berhasil diselesaikan dengan status **100% PASS**.

### 5. Verifikasi Benteng Pelindung Error (*Error Boundary & Failsafe*)
- Mengonfirmasi keberadaan *error handler* global pada `main.py` melalui `application.add_error_handler(error_handler)`.
- Jika terjadi kesalahan logika tak terduga pada salah satu pengguna, *exception* akan tercatat di log tanpa mematikan *polling* bot untuk ribuan pengguna lainnya.

### 6. Pemecahan Commit Terstruktur (*Atomic Commits*)
Seluruh perubahan yang sebelumnya menumpuk di *working tree* dikelompokkan dan di-commit secara terpisah:
1. `chore(git)`: Pembaruan `.gitignore` dan pembersihan file artefak *cache*.
2. `feat(db)`: *Resilience* koneksi Turso, logika *retry* otomatis, dan skema tabel baru.
3. `feat(kontrak)`: Pembaruan sistem kontrak, tombol interaktif, dan penutupan otomatis sesi presensi.
4. `feat(promo)`: Validasi instan tautan LPM, antrean verifikasi interaktif, dan penguncian status *processing*.
5. `feat(charyarthi)`: Penyesuaian divisi, jabatan staf, dan konfigurasi skema pilihan.
6. `fix(commands)`: Perbaikan perintah `/chat`, *routing caption*, pesan media, filter `/all`, dan pembaruan dokumentasi.
7. `test & docs`: Penambahan suite pengujian otomatis dan log tugas 095–117.
