# Task 138: QA Audit Mendalam & Security Hardening Fitur Ijazah & Transkrip

## Ringkasan Eksekutif
Melakukan Quality Assurance (QA) mendalam dan audit celah keamanan terhadap alur penerbitan ijazah dan transkrip shishya (`bot/graduation_excel.py`, `bot/transkrip_card.py`, `bot/ijazah_card.py`, `bot/handlers/graduation.py`). Berhasil mengidentifikasi dan menutup 6 celah kritis meliputi proteksi identitas (IDOR), isolasi pasfoto dokumen, mitigasi pemblokiran event loop async, optimasi I/O font & kompresi PNG, serta ketahanan file lock Excel di Windows.

---

## Rincian Temuan Celah & Perbaikan

### 1. [Security - IDOR] Celah Pembobolan Transkrip/Ijazah via First Name Telegram
- **Celah**: Pada fungsi `_find_student()`, jika user tidak memiliki NIM resmi di `profile_json`, sistem melakukan fallback mencocokkan `row["first_name"]` menggunakan substring match (`needle in s.nama`). Akibatnya, user publik atau orang asing yang mengubah nama depan Telegram-nya menjadi "Al", "Ad", "Ze", dll dapat melihat dan mengunduh seluruh transkrip dan ijazah mahasiswa resmi yang bersangkutan.
- **Perbaikan**:
  - Menghapus pencarian liar berbasis `first_name` Telegram.
  - Memberlakukan otorisasi ketat: User berstatus `ROLE_PUBLIC` ditolak sebelum dokumen diproses.
  - Self-service (`/transkrip` dan `/ijazah` tanpa argumen) **hanya boleh** mencocokkan `student_id` (NIM) resmi dari profil terverifikasi, atau nama lengkap resmi (`full_name`) dengan pencocokan persis (*exact match*).
  - Pencarian fleksibel hanya diizinkan untuk Admin/Owner dengan parameter eksplisit (`/transkrip <NIM/Nama>`).

### 2. [Identity Bug] Pasfoto Admin Tertempel pada Dokumen Shishya Target
- **Celah**: Saat Admin mengecek transkrip/ijazah mahasiswa lain (misal: `/transkrip 2004010093`), kode sebelumnya mengunduh foto dari `profile` dan `uid` pemohon perintah (yaitu Admin). Hal ini menyebabkan dokumen resmi mahasiswa tersebut tercetak dengan foto Admin!
- **Perbaikan**:
  - Jika perintah dijalankan dengan target NIM oleh Admin, sistem mencari akun mahasiswa target di tabel `users` via query JSON (`json_extract(profile_json, '$.student_id') = ?`).
  - Mengunduh foto asli milik mahasiswa target. Jika mahasiswa belum memiliki foto, sistem mempertahankan motif biru elegan default template ijazah/transkrip tanpa tertukar dengan foto Admin.

### 3. [Performance] Pemblokiran Event Loop pada `/export_kelulusan`
- **Celah**: Loop ekspor 21 mahasiswa $\times$ 2 dokumen (total 42 rendering grafis PNG) dijalankan secara sinkron di thread utama asyncio, memicu freeze/hang pada bot selama 15–20 detik dan menunda pesan dari seluruh pengguna Telegram lain.
- **Perbaikan**:
  - Memindahkan seluruh proses batch export CPU-bound ke background thread terpisah menggunakan `await asyncio.to_thread(_sync_export_documents, graduates, OUTPUT_DIR)`.
  - Proses pembuatan ZIP juga diisolasi di worker thread.

### 4. [Performance] Cache Font di Memori & Penghapusan `optimize=True`
- **Celah**:
  - `_load_font()` membaca file `.ttf` dari disk setiap kali fungsi render dipanggil.
  - Pemanggilan `im.save(out, format="PNG", optimize=True)` memicu kompresi exhaustive PNG yang memperlambat render hingga $\sim 1.050\text{ ms}$ per dokumen dengan selisih ukuran file $<5\%$.
- **Perbaikan**:
  - Menambahkan in-memory font cache `_FONT_CACHE` dan in-memory LRU cache `_CACHE` (kapasitas 64 item) pada `transkrip_card.py` dan `ijazah_card.py`.
  - Menghapus flag `optimize=True`, memangkas durasi render dari 1.050 ms menjadi $\sim 310\text{ ms}$ (3x lebih cepat), dan **0 milidetik** pada cache hit.

### 5. [Resilience] Penanganan Windows Exclusive File Lock pada Excel
- **Celah**: Jika administrator sedang membuka file `Template IPK.xlsx` di Microsoft Excel di Windows, Windows mengunci file secara eksklusif sehingga library `openpyxl` melempar `PermissionError`.
- **Perbaikan**:
  - Ditambahkan penanganan exception `PermissionError`: Jika file utama terkunci, sistem secara otomatis menyalin file ke temporary file terisolasi (`tempfile.NamedTemporaryFile`) lalu mem-parsing dari salinan tersebut tanpa mengganggu proses Excel yang sedang terbuka.

### 6. [Data Integrity] Kelengkapan Alias Gelar Akademik
- **Celah**: `DEGREE_MAP` pada `ijazah_card.py` sebelumnya hanya mengenali nama panjang jurusan formal (`ilmu kimia`, `ilmu fisika`, `seni musik`). Jika nama jurusan ditulis variasi pendek (`kimia`, `fisika`, `musik`), gelar jatuh ke fallback generik (*Sarjana Kimia*).
- **Perbaikan**: Menambahkan seluruh alias singkatan dan nama umum ke dalam kamus pemetaan gelar akademik resmi.

---

## Hasil Pengujian QA
- Seluruh 30 mahasiswa diuji layout rendering teks (Nama, NIM, Jurusan, Fakultas, 4 Matkul Akademik, IPK, Predikat, 3 UKM, dan IKK) tanpa ada overflow atau tumpang tindih piksel.
- Pengujian keamanan (`test_vulnerabilities.py`) memvalidasi bahwa percobaan klaim transkrip orang lain oleh user non-NIM berhasil diblokir 100%.
- Kepatuhan isolasi QA Telegram: tidak ada pesan pengujian yang terkirim ke pengguna publik.

