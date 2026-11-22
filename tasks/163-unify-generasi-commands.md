# Task 163: Unifikasi dan Restrukturisasi Perintah Manajemen Generasi

## 1. Deskripsi & Latar Belakang Masalah
Sebelumnya, sistem memiliki variasi perintah terkait generasi yang terpisah dan membingungkan:
- `/tutup_generasi` dan `/tutupgenerasi`
- `/setgenerasi` dan `/set_generasi`

User meminta untuk menyatukan dan merapikan struktur menu perintah generasi:
1. Menghapus alias `/tutupgenerasi`.
2. Mengubah `/tutup_generasi` menjadi `/generasi_tutup`.
3. Mengubah `/setgenerasi` menjadi `/generasi` yang menampilkan status generasi aktif saat ini beserta panduan sub menu (`/generasi_atur` dan `/generasi_tutup`).
4. Menghapus alias `/set_generasi`.
5. Mengeset nomor generasi menggunakan `/generasi_atur <nomor>` (contoh: `/generasi_atur 1`).

## 2. Rincian Perubahan Teknis
### A. Handler Perintah (`bot/handlers/commands.py`)
- **`cmd_generasi`**:
  - Dibatasi khusus Owner (`is_owner`).
  - Mengambil setting `current_generasi` dari database (default `"1"`).
  - Menampilkan ringkasan status generasi aktif dan daftar sub-menu:
    - `• <code>/generasi_atur &lt;nomor&gt;</code> — Mengatur nomor generasi aktif sistem.`
    - `• <code>/generasi_tutup [konfirmasi]</code> — Menutup generasi akademik & meluluskan seluruh mahasiswa aktif ke Purna Shishya (Alumni).`
- **`cmd_generasi_atur`**:
  - Dibatasi khusus Owner (`is_owner`).
  - Jika tanpa argumen, menampilkan nomor generasi saat ini dan panduan sintaks penggunaan.
  - Memvalidasi argumen bernilai angka integer positif $> 0$.
  - Memperbarui setting `current_generasi` di tabel `bot_settings` Turso dan mengirimkan konfirmasi.
  - Menyediakan alias internal `cmd_setgenerasi = cmd_generasi_atur`.
- **`cmd_generasi_tutup`**:
  - Dibatasi khusus Owner (`is_owner`).
  - Menghitung jumlah mahasiswa aktif (`student` dan `bem`).
  - Jika dipanggil tanpa konfirmasi, menampilkan pratinjau dan instruksi: `Ketik <code>/generasi_tutup konfirmasi</code> untuk mengeksekusi penutupan generasi.`
  - Jika dikonfirmasi, mengeksekusi `mass_set_role_purna` untuk meluluskan seluruh mahasiswa aktif ke Purna Shishya, membukukan SKS, mempertahankan NIM, membersihkan kelas/UKM, dan mengirimkan notifikasi.
  - Menyediakan alias internal `cmd_tutup_generasi = cmd_generasi_tutup`.
- **`cmd_help_owner`**:
  - Memperbarui ensiklopedia wewenang Owner:
    - `• <code>/generasi</code> — Status generasi aktif & panduan sub menu generasi.`
    - `• <code>/generasi_atur &lt;nomor&gt;</code> — Mengatur nomor generasi aktif sistem (contoh: <code>/generasi_atur 1</code>).`
    - `• <code>/generasi_tutup [konfirmasi]</code> — Menu interaktif penutupan generasi & meluluskan seluruh mahasiswa aktif ke Purna Shishya.`

### B. Pendaftaran Handler (`bot/handlers/register.py`)
- Menghapus pendaftaran `CommandHandler("tutupgenerasi", ...)` dan `CommandHandler("set_generasi", ...)`.
- Mendaftarkan handler resmi:
  - `CommandHandler("generasi", commands.cmd_generasi)`
  - `CommandHandler("generasi_atur", commands.cmd_generasi_atur)`
  - `CommandHandler("generasi_tutup", commands.cmd_generasi_tutup)`

### C. Dokumentasi & Skema (`docs/`)
- **`docs/commands.md`**: Mengganti seksi `/tutup_generasi`, `/tutupgenerasi`, `/setgenerasi`, `/set_generasi` dengan `/generasi`, `/generasi_atur <nomor>`, dan `/generasi_tutup [konfirmasi]`.
- **`docs/architecture.md`**: Memperbarui referensi arsitektur kelulusan massal menjadi `/generasi_tutup [konfirmasi]`.

### D. Pengujian & Verifikasi Mutu (`tests/`)
- **`tests/test_warkat.py`**: Memperbarui `test_cmd_setgenerasi_owner` untuk menguji hak akses dan respon `cmd_generasi`, `cmd_generasi_atur`, serta alias `cmd_setgenerasi`.
- **`tests/test_mass_setrole_purna.py`**: Memperbarui alur tes penutupan generasi untuk menggunakan `cmd_generasi_tutup` dan mengecek teks `/generasi_tutup konfirmasi`.
- **`tests/test_help_and_export_json.py`**: Memperbarui asersi `/help_owner` untuk mencakup `/generasi`, `/generasi_atur`, dan `/generasi_tutup`.
- **`tests/test_qa_master_audit.py`**: Menyesuaikan alur audit interaktif penutupan generasi ke `/generasi_tutup`.

## 3. Hasil Pengujian
1. **Pytest Regression Suite**:
   ```
   tests/test_warkat.py::test_cmd_setgenerasi_owner PASSED
   tests/test_mass_setrole_purna.py::test_command_tutup_generasi_flow PASSED
   tests/test_help_and_export_json.py::test_help_view_and_help_owner PASSED
   ======================== 18 passed in 3.39s =========================
   ```
2. **Master QA Audit (93 Tests)**:
   ```
   ==================================================================
   AUDIT EXECUTION SUMMARY in 1.79s:
   Total Tests Executed: 93
   PASSED: 93 | FAILED: 0 | UNVERIFIED: 0
   Discovered Bugs: 0
   ==================================================================
   ```
