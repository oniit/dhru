# 127: Production-Grade System QA & Verification (docs/qa.md)

## Latar Belakang & Tujuan
Menjalankan audit Quality Assurance (QA) mendalam dan menyeluruh pada seluruh subsistem Bot Dhruva sesuai protokol spesifikasi `docs/qa.md`. Audit difokuskan untuk membuktikan stabilitas alur registrasi Chāryārthī (calon staf), proteksi keyword rahasia promo LPM, pencegahan overflow karakter Telegram (>4096 char), atomisitas saldo Agra ledger, integritas presensi, dan security guard peran pengguna (RBAC).

## Cakupan & Komponen yang Diuji

### 1. Akun & Lifecycle Onboarding (`test_qa_account_and_onboarding_lifecycle`)
- `/start`: Memastikan user baru terdaftar dengan peran `ROLE_PUBLIC`, state step direset ke `None`, profil telegram tersimpan rapi tanpa error serialisasi JSON.
- `/charyarthi`: Memvalidasi pembukaan oprec via setting dinamis, mengarahkan calon pendaftar ke step `CHARYARTHI_NAME`.
- `/cancel`: Memastikan pembatalan di tengah jalan membersihkan state aktif (`onboarding_step` menjadi `None`) tanpa meninggalkan sampah sesi.

### 2. End-to-End Chāryārthī Lifecycle (`test_qa_charyarthi_full_e2e_flow`)
- Input identitas nama pendaftar (`CHARYARTHI_NAME`).
- Pemilihan divisi formasi (`CHARYARTHI_DIV:d_editor`) dan penguncian pilihan (`charyarthi_div`).
- Input alasan pendaftaran (`CHARYARTHI_REASON`) dengan pesan teks panjang.
- Penyimpanan dan pengeditan jawaban esai bertahap (`CHARYARTHI_ANS:`).
- Fitur reset jawaban (`charyarthi:reset:d_editor`) membersihkan jawaban esai sebelumnya.
- Dynamic answer preview (`charyarthi:preview`) dengan HTML safe-escaping tanpa entity parsing crash.
- Notifikasi SDM Channel (`SDM_CH_ID`) berupa dispatch card rapi (termasuk divisi tanpa soal esai).
- Forwarding berkas pendaftaran ke `PENDAFTAR_CH_ID` dengan pembatasan panjang teks dan threading jawaban panjang.
- Approval workflow oleh admin (`charyarthi:acc:{uid}:1`) mengesahkan pendaftar menjadi peran `ROLE_INTERNAL`, mencatat `position_detail`, dan membersihkan status `PENDING`.

### 3. Keamanan & Authorization Guard (`test_qa_security_and_authorization_guards`)
- User publik (`ROLE_PUBLIC`) diblokir dari akses `/soal`.
- User publik diblokir dari eksekusi callback ACC/Tolak pendaftar.
- Validasi strict RBAC mencegah eskalasi privilege atau IDOR manipulation.

### 4. Presensi & Role Integrity (`test_qa_presensi_and_roles_integrity`)
- Pembuatan sesi presensi kelas/event.
- Pencatatan kehadiran user yang sah.
- Pencegahan double-attendance untuk sesi yang sama.
- Validasi status penutupan sesi otomatis.

### 5. Agra Ledger Atomicity & Integrity (`test_qa_agra_ledger_atomicity`)
- Mutasi penambahan saldo dan transfer antar pengguna.
- Verifikasi saldo ledger non-negatif dan konsisten via `agra_total`.
- Pencatatan debit/kredit transaksi berpasangan pada tabel `agra_ledger`.

## Hasil Eksekusi Uji
- `tests/test_full_system_production_qa.py`: 5 / 5 PASSED (100%)
- `tests/test_charyarthi.py`: 10 / 10 PASSED (100%)
- `tests/test_promo_lpm.py`: 5 / 5 PASSED (100%)
- Total pengujian: 20 skenario komprehensif berhasil dieksekusi pada basis data remote Turso.

## Kesimpulan
Sistem telah memenuhi seluruh kriteria verifikasi ketat `docs/qa.md`. Seluruh bug terkait Chāryārthī (jawaban panjang terpotong, reset jawaban tersisa, kebocoran keyword LPM, dan perpindahan konfigurasi `SDM_CH_ID`) telah tuntas diperbaiki dan divalidasi aman untuk operasional produksi.
