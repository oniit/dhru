# Task 165: Transformasi `/gencode` Menjadi Dashboard & Sub Menu Interaktif

## 1. Deskripsi & Latar Belakang
User meminta perintah `/gencode` dibuatkan struktur sub menu interaktif seperti halnya restrukturisasi pada menu `/generasi`. Sebelumnya, memanggil `/gencode` tanpa argumen secara otomatis menghasilkan 1 kode peran `student` tanpa panduan atau ringkasan status stok.

## 2. Rincian Perubahan Teknis
### A. Handler Perintah `/gencode` (`bot/handlers/commands.py`)
- Jika dipanggil **tanpa argumen** oleh Owner:
  - Mengambil statistik live jumlah kode akses standar yang belum diklaim (`SELECT COUNT(*) FROM access_codes WHERE used_by IS NULL`).
  - Mengambil statistik live jumlah Warkat Kehormatan yang belum digunakan (`SELECT COUNT(*) FROM warkat_codes WHERE used_by IS NULL`).
  - Menampilkan dashboard status stok dan daftar panduan sub menu:
    - `• <code>/gencode &lt;jumlah&gt; [role]</code>`
    - `• <code>/gencode_avail</code>`
    - `• <code>/gencode_warkat [jumlah]</code>`
    - `• <code>/gencode_warkat_avail</code>`
  - Menyertakan inline keyboard tombol interaktif:
    - `[📦 Kode Standar Tersedia (N)]` (`callback_data="gencode:avail_std"`)
    - `[📜 Warkat Kehormatan Tersedia (M)]` (`callback_data="gencode:avail_wkt"`)
- Jika dipanggil **dengan argumen** (misal `/gencode 5 student` atau `/gencode 2 bem`):
  - Mempertahankan backward compatibility penuh untuk langsung membuat kode akses dengan jumlah dan peran target yang ditentukan.

### B. Callback Interaktif & Navigasi Tombol Kembali (`bot/handlers/commands.py`)
- `gencode:avail_std`: Menampilkan daftar kode akses standar yang belum diklaim, dilengkapi tombol `[⬅️ Kembali]` (`callback_data="gencode:menu"`).
- `gencode:avail_wkt`: Menampilkan daftar warkat kehormatan yang belum digunakan beserta status keaktifan jalur Charya (60 hari) & Pravesa (2 generasi), dilengkapi tombol `[⬅️ Kembali]` (`callback_data="gencode:menu"`).
- `gencode:menu`: Mengembalikan tampilan pesan ke dashboard utama `/gencode`.

### C. Optimalisasi Pembacaan Database Turso (`bot/database.py`)
- Menambahkan indeks DDL permanen:
  `CREATE INDEX IF NOT EXISTS idx_access_codes_used_by ON access_codes(used_by);`
  pada skema DDL statis dan fungsi `init_db` guna menjamin kueri hitung stok dan `gencode_avail` tidak melakukan Full Table Scan.

### D. Dokumentasi & Panduan Owner (`docs/commands.md` & `cmd_help_owner`)
- Memperbarui deskripsi perintah `/gencode` di ensiklopedia panduan wewenang Owner (`cmd_help_owner`) dan `docs/commands.md`.

### E. Pengujian (`tests/test_public_menu.py`)
- Ditambahkan fungsi tes `test_gencode_menu_and_callbacks`:
  - Validasi otorisasi Owner.
  - Tampilan dashboard sub-menu dan inline keyboard.
  - Interaktivitas tombol callback dan tombol kembali.
  - Pembuatan kode akses dengan argumen peran dan kuota.

## 3. Hasil Pengujian
- `pytest tests/test_public_menu.py tests/test_warkat.py tests/test_mass_setrole_purna.py tests/test_help_and_export_json.py -v`: **20 passed**.
- `python tests/test_qa_master_audit.py`: **93 passed, 0 failed**.
