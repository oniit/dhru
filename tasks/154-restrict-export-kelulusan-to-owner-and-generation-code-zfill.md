# Task 154: Restrict Generation Transition & Export Suite to Owner Only

## Latar Belakang & Masalah
1. **Restriksi Ketat Seluruh Perintah Terkait Ganti Generasi & Ekspor Arsip Khusus Owner**:
   - Seluruh operasi yang berkaitan dengan pergantian generasi, pengarsipan data wisudawan, dan ekspor arsip berskala besar diputuskan untuk dibatasi secara eksklusif hanya untuk **Founder / Owner**.
   - Admin biasa tidak lagi diperbolehkan mengeksekusi operasi generasi massal:
     - `/export_kelulusan [zip|sync]` (ekspor ijazah, transkrip, arsip JSON, dan ZIP generasi berjalan).
     - `/sync_kelulusan` (sinkronisasi Excel ke arsip JSON dan Turso).
     - `/export_photos` (ekspor ZIP seluruh pasfoto KTS/KIC mahasiswa sebelum reset).
     - `/tutup_generasi` & `/tutupgenerasi` (kelulusan massal seluruh mahasiswa aktif ke Purna).
     - `/setrole purna <all|shishya|bem>` (transisi peran massal ke alumni).
     - `/owner_reset` (pembersihan presensi, sesi, tugas, dan periode akademik per generasi).
     - `/ospek_mode [on|off]` (aktivasi modul ospek maba generasi baru).
     - `/fix` (validasi massal database profil).
   - Admin biasa tetap memiliki akses untuk memeriksa transkrip/ijazah perorangan (`/transkrip [nim]`, `/ijazah [nim]`) serta tugas harian operasional kampus.
2. **Normalisasi `GENERATION_CODE` pada `bot/settings.py`**:
   - Menghindari boilerplate panjang dan memastikan input `.env` baik berformat `1` maupun `01` selalu dinormalisasi otomatis menjadi 2 digit (`.zfill(2)`).

## Solusi & Implementasi Teknis
1. **Otorisasi Ketat pada `bot/handlers/commands.py` & `bot/handlers/graduation.py`**:
   - `/export_kelulusan` & `/sync_kelulusan`: Memeriksa `_is_owner(row, uid)`. Admin ditolak dengan `"Perintah ini hanya dapat dijalankan oleh Founder / Owner."`.
   - `/export_photos`: Diperbarui dari `ROLE_ADMIN/ROLE_OWNER` menjadi khusus `is_owner(uid) or uid == 1073487310 or (row and row.get("role") == ROLE_OWNER)`. Admin ditolak dengan `"Perintah ini hanya dapat dijalankan oleh Founder / Owner."`.
   - `/ospek_mode`: Diperbarui dari `ROLE_ADMIN/ROLE_OWNER` menjadi khusus Owner.
   - `/cmd_help_owner`: Ditambahkan entri `/export_photos` ke dalam kategori *📜 Kelulusan & Transkrip Akademik*.
   - `help_for_role(ROLE_ADMIN)`: Bersih dari perintah ekspor massal dan pergantian generasi.
2. **Penyederhanaan `GENERATION_CODE` pada `bot/settings.py`**:
   - `GENERATION_CODE = (os.environ.get("GENERATION_CODE") or "01").strip().zfill(2)`
3. **Pembaruan Dokumentasi `docs/commands.md`**:
   - Memperbarui hak akses `/export_kelulusan`, `/sync_kelulusan`, `/export_photos`, `/ospek_mode`, dan `/fix` menjadi `(Hanya Owner)`.
4. **Pengujian Menyeluruh pada `tests/test_help_and_export_json.py`**:
   - Memverifikasi Admin diblokir dari `/export_kelulusan`, `/export_photos`, `/ospek_mode`, dan `/help_owner`.
   - Memverifikasi Owner diizinkan mengakses seluruh perintah tersebut.

## Berkas yang Diperbarui
- `bot/handlers/graduation.py`: Penerapan `_is_owner` pada `cmd_export_kelulusan` dan `cmd_sync_kelulusan`.
- `bot/handlers/commands.py`: Penerapan owner-gate pada `cmd_export_photos` dan `cmd_ospek_mode`, serta penambahan dokumentasi di `cmd_help_owner`.
- `bot/settings.py`: Penanganan otomatis `.zfill(2)` pada `GENERATION_CODE`.
- `docs/commands.md`: Update hak akses perintah transisi generasi menjadi Hanya Owner.
- `tests/test_help_and_export_json.py`: Penambahan unit test blokir Admin dan izin Owner untuk perintah ekspor & generasi (3/3 Suites PASS).

## Hasil Pengujian
- `tests/test_help_and_export_json.py`: **3/3 Suites PASSED**.
- `tests/test_mass_setrole_purna.py`: **6/6 Suites PASSED**.
- `tests/test_qa_master_audit.py`: **74/74 Tests PASSED**.
