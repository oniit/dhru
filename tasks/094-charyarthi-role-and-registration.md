# Task 094: Konsep & Implementasi Role Chāryārthī (Pendaftar Charya / Calon Staf)

## Apa yang Dikerjakan
1. **Definisi Role & Hierarki**:
   - Menambahkan konstanta `ROLE_CHARYARTHI = "charyarthi"` pada `bot/database.py`.
   - Mengatur urutan hierarki di dalam `ROLES_ORDER` menjadi:
     `Owner > Admin > Internal > BEM > Student > Maba > Charyarthi > Public`.
   - Menambahkan mapping tampilan di `role_display` (`bot/handlers/common.py`) menjadi `Chāryārthī`.
2. **Konfigurasi & Pengaturan Divisi**:
   - Menambahkan variabel environment di `bot/settings.py`:
     - `CHARYARTHI_GFORM_LINK`: Tautan resmi Google Form formulir berkas calon staf.
     - `CHARYARTHI_OPREC_OPEN`: Saklar status buka/tutup pendaftaran OPREC staf.
   - Menambahkan fungsi pembantu:
     - `get_charyarthi_divisions()`: Mengambil daftar divisi staf yang dibuka (mengecualikan jabatan struktural tinggi seperti rektor, dekan, dsb).
     - `get_division_label(div_id)`: Mengambil label nama divisi dari `choices.yaml`.
   - Menambahkan field profil di `config/profile_fields.yaml`:
     - `target_division_1`: Divisi Pilihan 1 (Utama).
     - `target_division_2`: Divisi Pilihan 2 (Cadangan, opsional/bisa dilewati).
3. **Alur Pendaftaran Terbuka (Open Registration)**:
   - Pada menu `/start` untuk role `public`, ditambahkan tombol interaktif `[ 📝 Pendaftaran Charya (Staf) ]` (`charyarthi:start`).
   - Bot meminta input Nama Lengkap pelamar (`CHARYARTHI_NAME` di `bot/handlers/messages.py`).
   - Pelamar memilih **Divisi Utama (Pilihan 1)** via tombol inline.
   - Pelamar memilih **Divisi Cadangan (Pilihan 2)** atau menekan **`[ ⏭ Lewati / Cukup 1 Divisi ]`**.
   - Bot menyajikan tautan Google Form dan instruksi syarat wajib **minimal 1x Promosi** (`/lpm` atau `/story`).
   - Ketika pelamar menekan `[ 🚀 Submit Pendaftaran ]`:
     - Bot memverifikasi riwayat promo valid (`count_valid_promos >= 1`).
     - Jika belum ada promo valid, bot memunculkan pop-up peringatan.
     - Jika sudah valid, role pengguna resmi diubah menjadi `ROLE_CHARYARTHI`, status diset ke `PENDING`, dan rekap pendaftar diteruskan ke channel penampung admin (`PENDAFTAR_CH_ID`) dengan tombol aksi `[ ✅ Terima ]` dan `[ ❌ Tolak ]`.
4. **Mekanisme Seleksi & Keputusan (Accept / Reject)**:
   - **Jika Diterima (`charyarthi:acc` atau `/acc_charyarthi <id> [1|2]`)**:
     - Role pengguna di-upgrade menjadi `ROLE_INTERNAL`.
     - Divisi yang diterima disimpan ke dalam `position_detail` profil pengguna.
     - Notifikasi DM dikirimkan ke pengguna dengan arahan menandatangani `/kontrak` kerja staf.
   - **Jika Ditolak (`charyarthi:rej` atau `/reject_charyarthi <id>`)**:
     - Role pengguna di-rollback kembali ke `ROLE_PUBLIC`.
     - Notifikasi apresiasi dan penolakan ramah dikirimkan via DM.
5. **Integrasi Perintah Administratif & Saklar Dinamis (Mirip `/settings_game`)**:
   - `/setting_charyarthi` / `/settings_charyarthi`: Menu interaktif kontrol saklar rekrutmen via tombol inline (`✅`/`❌`).
     - **Master Switch**: Buka/tutup seluruh pendaftaran secara instan (`charyarthi_oprec_open`).
     - **Per-Divisi Switch**: Buka/tutup divisi tertentu secara selektif (`charyarthi_div_{div_id}`). Hanya divisi aktif (`✅`) yang akan muncul saat pendaftar memilih divisi.
     - **Bulk Actions**: Tombol "🟢 Buka Semua" dan "🔴 Tutup Semua".
     - Persistensi state disimpan di tabel remote `bot_settings` Turso secara real-time.
     - Diizinkan untuk Admin Elevated dan chat grup `PETINGGI_GID`.
   - `/daftar charyarthi`: Menampilkan daftar semua pelamar calon staf yang sedang aktif.
   - `/detail charyarthi`: Menampilkan detail data pendaftar staf.
   - `/all charyarthi <pesan>`: Mention/tag massal ke seluruh pendaftar calon staf.
   - `/gencode`: Membuka dukungan target role `charyarthi`.
   - `/acc_charyarthi <id> [1|2]`: Terima calon staf manual.
   - `/reject_charyarthi <id>`: Tolak calon staf manual (rollback ke public).
6. **Pengujian Unit**:
   - Membuat file tes baru `tests/test_charyarthi.py` untuk menguji hierarki, mapping label, siklus pendaftaran, promosi, penerimaan, rollback penolakan ke publik, dan saklar dinamis master/divisi.

## Mengapa Dikerjakan
- Kampus/komunitas membutuhkan jalur rekrutmen terbuka untuk staf baru (Charya) tanpa memberikan hak akses internal secara prematur.
- Menggantikan masa probation yang panjang di dalam bot dengan pengisian berkas Google Form terstruktur dan syarat verifikasi sebaran promosi (LPM/Story), sehingga efisien dan menyatu dengan sistem validasi bot yang sudah ada.

## Alur Teknis
1. `User` (Public) -> `/start` -> `charyarthi:start` -> Input nama -> Pilih Divisi 1 & 2 -> Buka GForm & sebar promo -> `charyarthi:submit`.
2. `Checker` memvalidasi link LPM/Story -> `count_valid_promos` bertambah -> Submit sukses -> Role menjadi `ROLE_CHARYARTHI` -> Terusan masuk ke `PENDAFTAR_CH_ID`.
3. Admin meninjau berkas di Spreadsheet GForm -> Klik tombol terima/tolak di Telegram channel -> Role di-update ke `ROLE_INTERNAL` (lanjut `/kontrak`) atau di-rollback ke `ROLE_PUBLIC`.
