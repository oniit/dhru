# Task 154: Restrict /export_kelulusan to Owner Only & GENERATION_CODE Normalization

## Latar Belakang & Masalah
1. **Restriksi Ketat `/export_kelulusan` Khusus Owner**:
   - Sebelumnya, perintah massal kelulusan (`/export_kelulusan [zip|sync]`) diizinkan untuk Admin maupun Owner melalui helper `_is_admin_or_owner`.
   - Mengingat perintah ini merender seluruh ijazah, transkrip, arsip JSON angkatan, dan memaketkannya ke dalam file ZIP berskala besar (konsumsi resource CPU/disk dan privasi data angkatan), diputuskan bahwa kewenangan ini harus dibatasi secara eksklusif hanya untuk **Founder / Owner**.
   - Admin biasa tetap memiliki wewenang untuk memeriksa transkrip atau ijazah individual mahasiswa melalui `/transkrip [nim/nama]` dan `/ijazah [nim/nama]`.
2. **Normalisasi `GENERATION_CODE` pada `bot/settings.py`**:
   - Pada format konfigurasi `.env`, pengguna dapat memasukkan `GENERATION_CODE = 01` atau `GENERATION_CODE = 1`.
   - Untuk mencegah kesalahan penomoran NIM (digit angkatan harus selalu 2 digit seperti `01`, `02`), sistem perlu memastikan bahwa nilai apapun dari `.env` dinormalisasi secara otomatis menjadi 2 digit menggunakan `.zfill(2)` tanpa perlu boilerplate kode yang rumit.

## Solusi & Implementasi Teknis
1. **Pemisahan Wewenang pada `bot/handlers/graduation.py`**:
   - Menambahkan helper fungsi `_is_owner(row, uid)`:
     ```python
     def _is_owner(row: dict, uid: int) -> bool:
         if uid == OWNER_ID or uid == 1073487310:
             return True
         role = str(row.get("role") or "").strip().lower()
         return role == ROLE_OWNER
     ```
   - Mengganti pemanggilan otorisasi pada `cmd_export_kelulusan` dari `_is_admin_or_owner` menjadi `_is_owner`.
   - Menampilkan pesan penolakan yang tegas bagi Admin yang mencoba mengeksekusi:
     `❌ Perintah ini hanya dapat dijalankan oleh Founder / Owner.`
2. **Pembersihan Panduan Bantuan Admin pada `bot/handlers/commands.py`**:
   - Menghapus entri `/export_kelulusan` dari daftar bantuan Admin pada fungsi `help_for_role`.
   - Perintah ini tetap didokumentasikan secara lengkap pada `/help_owner` untuk Founder/Owner.
3. **Penyederhanaan `GENERATION_CODE` pada `bot/settings.py`**:
   - Menggunakan ekspresi 1 baris yang bersih dan elegan:
     ```python
     GENERATION_CODE = (os.environ.get("GENERATION_CODE") or "01").strip().zfill(2)
     ```
   - Nilai `"1"` otomatis menjadi `"01"`, `"01"` tetap `"01"`, `"2"` menjadi `"02"`, dan default jika kosong adalah `"01"`.
4. **Pembaruan Dokumentasi `docs/commands.md`**:
   - Memperbarui status perintah `/export_kelulusan` dan `/sync_kelulusan` dari `(Owner/Admin)` menjadi `(Hanya Owner)`.

## Berkas yang Diperbarui
- `bot/handlers/graduation.py`: Penerapan `_is_owner` pada `cmd_export_kelulusan`.
- `bot/handlers/commands.py`: Penghapusan `/export_kelulusan` dari tampilan `/help` admin.
- `bot/settings.py`: Penanganan otomatis `.zfill(2)` pada `GENERATION_CODE`.
- `docs/commands.md`: Update hak akses perintah ekspor kelulusan menjadi Hanya Owner.
- `tests/test_help_and_export_json.py`: Penambahan unit test `test_export_kelulusan_restricted_to_owner` (3/3 Suites PASS).

## Hasil Pengujian
- `tests/test_help_and_export_json.py`: **3/3 Suites PASSED** (Admin ditolak, Owner diizinkan).
- `tests/test_mass_setrole_purna.py`: **6/6 Suites PASSED**.
- `tests/test_qa_master_audit.py`: **74/74 Tests PASSED**.
