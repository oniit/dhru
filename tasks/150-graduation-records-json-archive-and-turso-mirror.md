# Task 150: Arsip Kelulusan Kumulatif Berbasis JSON & Mirroring Database Turso

## Ringkasan
Mengimplementasikan sistem penyimpanan data kelulusan shishya bertingkat (*dual-layer architecture*). Sistem memprioritaskan pembacaan cepat dari arsip JSON lokal (`data/graduation_records.json`) dengan *in-memory cache* untuk menjaga efisiensi kuota Turso (0 *rows read*), mengintegrasikan *auto-merge* data dari Excel acuan (`Template IPK.xlsx`), me-*mirror* data secara otomatis ke tabel `graduation_records` remote database Turso sebagai cadangan cloud terpusat, serta mengotomatiskan penamaan direktori paket dokumen kelulusan secara dinamis berdasarkan generasi berjalan (`GENERATION_CODE`).

---

## Latar Belakang & Masalah
1. **Beban Pemeliharaan Excel Lintas Generasi:**
   Sebelumnya, modul `bot/graduation_excel.py` membaca langsung file `assets/Template IPK.xlsx` pada setiap pemanggilan `/transkrip` dan `/ijazah`. Hal ini menuntut pengelola untuk terus menumpuk data kelulusan lama jika tidak ingin arsip wisudawan generasi sebelumnya hilang saat generasi baru masuk.
2. **Kebutuhan Fleksibilitas Pengelola:**
   Pengelola menginginkan agar file `Template IPK.xlsx` dapat diganti/ditimpa isinya hanya untuk mahasiswa generasi berjalan (tanpa harus menyisakan baris generasi sebelumnya), namun seluruh data kelulusan masa lalu tetap dapat diakses oleh alumni kapan pun.
3. **Optimasi Kuota Turso:**
   Sesuai aturan arsitektur basis data, pembacaan dokumen kelulusan yang sering dipanggil tidak boleh membebani kuota *rows read* Turso.

---

## Solusi & Perubahan yang Dilakukan

### 1. Model Serialisasi Data (`bot/graduation_excel.py`)
- Menambahkan metode `to_dict()` dan `from_dict()` pada dataclass `CourseGrade`, `ClubGrade`, dan `StudentGraduationData`.
- Mendaftarkan path arsip lokal permanen: `JSON_ARCHIVE_PATH = ROOT / "data" / "graduation_records.json"`.

### 2. Mekanisme Pembacaan Berprioritas & Auto-Merge (`bot/graduation_excel.py`)
- **Prioritas 1 (Read dari JSON/Cache):**
  Fungsi `get_student_by_nim()` dan `get_student_by_name()` selalu membaca data dari in-memory cache yang dimuat dari `data/graduation_records.json` (kecepatan lookup ~1-3 ms, 0 *rows read* ke Turso).
- **Auto-Merge dari Excel:**
  Fungsi `_sync_excel_into_archive()` memantau timestamp `EXCEL_PATH`. Jika ada spreadsheet baru masuk:
  - Seluruh wisudawan baru dibaca dan diberi label generasi berjalan (`GENERATION_CODE`).
  - Data di-merge ke dalam arsip tanpa menghapus data wisudawan dari generasi-generasi sebelumnya.
  - Hasil merge disimpan kembali secara atomik ke `data/graduation_records.json`.
- **Filtering Per Generasi:**
  Fungsi `get_all_graduates(generasi)` dan `get_all_students(generasi)` kini mendukung filter parameter generasi tertentu (contoh: `generasi="1"`, `generasi="2"`).

### 3. Redundansi Cloud (Turso Database Mirroring)
- **Skema DDL (`bot/database.py`):**
  Menambahkan tabel baru di `SCHEMA` dan migrasi:
  ```sql
  CREATE TABLE IF NOT EXISTS graduation_records (
      nim TEXT PRIMARY KEY,
      nama TEXT NOT NULL,
      generasi TEXT NOT NULL,
      data_json TEXT NOT NULL,
      created_at REAL NOT NULL,
      updated_at REAL NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_grad_records_nama ON graduation_records(nama);
  CREATE INDEX IF NOT EXISTS idx_grad_records_gen ON graduation_records(generasi);
  ```
- **Metode Database:**
  - `upsert_graduation_records(conn, records)`: Menyimpan/meng-update daftar record lulusan ke Turso secara atomik.
  - `get_all_graduation_records_from_db(conn, generasi)`: Mengambil seluruh record atau record per generasi dari database.
- **Helper Mirror & Restore:**
  - `mirror_archive_to_turso(conn, db, records)`: Mengirimkan salinan arsip JSON ke database Turso.
  - `restore_archive_from_turso_if_empty(conn, db)`: Memulihkan kembali file `data/graduation_records.json` dari Turso jika file lokal terhapus pada lingkungan deploy baru.

### 4. Handler Kelulusan & Perintah Baru (`bot/handlers/graduation.py` & `register.py`)
- **Direktori Output Dinamis:**
  Mengganti path hardcoded `kelulusan_gen1` dengan fungsi dinamis `_get_output_dir()` dan `_get_zip_path()` yang mengikuti variabel `GENERATION_CODE` dari environment (contoh: `kelulusan_gen1`, `kelulusan_gen2`, dst.).
- **Perintah Sinkronisasi:**
  - Menambahkan opsi `/export_kelulusan sync` dan shortcut `/sync_kelulusan` untuk mengeksekusi impor Excel ke arsip JSON dan me-mirror salinannya ke Turso DB tanpa perlu merender gambar PNG.
  - Saat `/export_kelulusan` atau `/export_kelulusan zip` dijalankan, proses render otomatis mengeksekusi *background task* mirroring ke Turso DB.

---

## Verifikasi & Pengujian
- Membuat file pengujian `tests/test_graduation_archive.py` yang memverifikasi:
  1. Serialisasi & deserialisasi dataclass kelulusan.
  2. Pencarian data via NIM 11 digit, NIM tanpa leading zero, nama lengkap, dan substring nama.
  3. Kemampuan *multi-generation merge* (menggabungkan data Gen 1 dan Gen 2 secara kumulatif).
  4. Penyimpanan dan pengambilan data mirroring SQLite/Turso.
  5. Filter kelulusan per generasi berjalan.
- **Hasil Pengujian:** Seluruh 5 rangkaian uji lulus bersih (100% PASS).
- **Arsip Awal:** Berhasil mengarsipkan 30 mahasiswa (21 lulusan) Gen 1 dari `Template IPK.xlsx` ke dalam `data/graduation_records.json` (31.753 bytes).

---

## Dokumentasi Terkait
- [docs/architecture.md](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/docs/architecture.md): Diperbarui pada Bagian 15 (*Graduation Pipeline & Dual-Layer Auto-Archive*).
- [docs/database.md](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/docs/database.md): Ditambahkan tabel 21 `graduation_records` beserta indeksnya.
- [docs/commands.md](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/docs/commands.md): Ditambahkan dokumentasi `/sync_kelulusan` dan opsi `/export_kelulusan sync`.
