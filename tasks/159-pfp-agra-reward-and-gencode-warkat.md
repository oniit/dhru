# Task 159: Reward Agra PFP Otomatis & Sistem Warkat Kehormatan (/gencode_warkat)

## Ringkasan Eksekutif
Task ini mengimplementasikan dua fitur utama sesuai instruksi dan diskusi bersama user:
1. **Reward Agra Otomatis untuk Forward Post `/pfp`**: Setiap postingan channel yang berhasil diforward ke channel penyimpanan (`KEEP_CH_ID`) secara otomatis memberikan reward **+1 Agra per post** ke akun pengguna tanpa batas harian.
2. **Sistem Warkat Kehormatan (`/gencode_warkat` & `/kode`)**: Sistem voucher/akses kode eksklusif untuk alumni/purnata terpilih yang menyediakan dua jalur istimewa dengan masa kedaluwarsa ganda (_dual-expiry_):
   - **Jalur Khusus Charya (Calon Staf)**:
     - Masa berlaku: **60 hari** sejak warkat digenerate (`now <= expires_charya`).
     - Bebas tugas promosi (LPM/Story) dan bebas seluruh tes esai tertulis.
     - Pendaftar langsung memilih **3 divisi peminatan** (Pilihan 1, Pilihan 2, Pilihan 3).
     - Pendaftar diarahkan untuk mengirim berkas CV (PDF/Gambar) ke akun bot resmi HR: **`@HRDhruvaBot`**.
     - Setelah memilih divisi dan mengirim CV, pendaftar mengonfirmasi pengiriman lamaran.
     - Notifikasi pendaftaran dikirim ke `PENDAFTAR_CH_ID` dan grup SDM (`SDM_CH_ID` / `SDM_GID`) dengan 3 tombol persetujuan (`charyarthi:acc:{uid}:1`, `:2`, `:3`) serta penolakan (`charyarthi:rej:{uid}`).
   - **Bebas Pravesa (Mahasiswa/Shishya)**:
     - Masa berlaku: Hingga **2 generasi** ke depan (`cur_gen <= max_generasi`).
     - Langsung diangkat menjadi **Shishya (Mahasiswa/`student`)** tanpa harus mengikuti kegiatan Ospek (Pravesa).

---

## Detail Perubahan Teknis

### 1. Reward Agra PFP (`bot/handlers/pfp.py`)
- Saat eksekusi forward berhasil (`forwarded_count > 0`):
  ```python
  await db.add_agra(
      conn,
      user_id=user_id,
      amount=forwarded_count,
      reason=f"Reward forward {forwarded_count} postingan via /pfp",
      actor_telegram_id=user_id
  )
  ```
- Pesan status penyelesaian diperbarui menampilkan perolehan Agra (misal: `Berhasil mem-forward 5 postingan (+5 Agra)`).
- Teks panduan tutorial `/pfp` diperbarui mencantumkan benefit reward Agra.

### 2. Skema & Metode Database (`bot/database.py`)
- **Tabel `warkat_codes`**:
  ```sql
  CREATE TABLE IF NOT EXISTS warkat_codes (
      code TEXT PRIMARY KEY,
      created_at REAL NOT NULL,
      created_by INTEGER NOT NULL,
      expires_charya REAL NOT NULL,
      created_gen INTEGER NOT NULL DEFAULT 1,
      max_generasi INTEGER NOT NULL,
      used_by INTEGER,
      used_at REAL,
      chosen_track TEXT,
      charya_div_1 TEXT,
      charya_div_2 TEXT,
      charya_div_3 TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_warkat_used_by ON warkat_codes(used_by);
  CREATE INDEX IF NOT EXISTS idx_warkat_created_at ON warkat_codes(created_at);
  ```
- **Metode Database Baru**:
  - `create_warkat_codes(conn, codes_data)`: Insert massal warkat baru.
  - `get_warkat_code(conn, code)`: Ambil data warkat (case-insensitive via `.upper()`).
  - `redeem_warkat_code(conn, code, user_id, chosen_track, div1, div2, div3)`: Eksekusi klaim warkat secara atomik dengan `WHERE code = ? AND used_by IS NULL`.
  - `get_available_warkat_codes(conn)`: Mengambil daftar warkat yang belum digunakan.
- **Pembersihan Data & Generasi**:
  - `reset_all_data_except_users`: Ditambahkan `DELETE FROM warkat_codes`.
  - `mass_set_role_purna`: Otomatis meng-increment nilai setting `current_generasi` saat generasi ditutup.

### 3. Handler Command & Callback (`bot/handlers/commands.py`)
- **Perintah Baru Owner**:
  - `/gencode_warkat [jumlah]` / `/genwarkat`: Membuat kode berformat `WARKAT-XXX-YYY`, menyetel `expires_charya = now + 60*86400` dan `max_generasi = current_generasi + 2`.
  - `/gencode_warkat_avail` / `/genwarkat_avail`: Menampilkan daftar warkat belum dipakai beserta status keaktifan masing-masing jalur.
  - `/help_owner`: Mencantumkan panduan penggunaan kedua perintah di atas.
- **Alur Interaktif Callback `handle_warkat_callback`**:
  - `warkat:cancel`: Membatalkan sesi penukaran.
  - `warkat:pravesa:{code}`: Validasi batas generasi -> redeem atomik -> set role `ROLE_STUDENT` -> notifikasi user, Owner, dan Backup channel.
  - `warkat:charya:{code}`: Validasi batas 60 hari -> inisialisasi pemilihan divisi 1.
  - `warkat:cdiv1:{code}:{did}`: Simpan pilihan 1 -> tampilkan opsi divisi 2 (eksklusi pilihan 1).
  - `warkat:cdiv2:{code}:{did}`: Simpan pilihan 2 -> tampilkan opsi divisi 3 (eksklusi pilihan 1 & 2).
  - `warkat:cdiv3:{code}:{did}`: Simpan pilihan 3 -> tampilkan ringkasan konfirmasi & instruksi pengiriman CV ke `@HRDhruvaBot`.
  - `warkat:csubmit:{code}`: Eksekusi redeem atomik -> set role `ROLE_CHARYARTHI` & profil `target_division_1/2/3` -> broadcast ke `PENDAFTAR_CH_ID` (dengan 3 tombol terima + 1 tolak) & `SDM_CH_ID`/`SDM_GID`.
- **Dukungan Pilihan Divisi Ketiga**:
  - Callback `charyarthi:acc:{uid}:3` dan perintah `/acc_charyarthi <uid> 3` diperbarui untuk menerima calon staf pada divisi pilihan ke-3.
  - `charyarthi:rej` dan `/reject_charyarthi` otomatis membersihkan `target_division_3` ke `None`.
  - Tampilan status pendaftaran Chāryārthī pada `/profil` menampilkan seluruh divisi pilihan yang didaftarkan.

### 4. Input Kode Terpadu (`bot/handlers/messages.py`)
- Fungsi `handle_input_code(update, context, raw_code)` mengecek kode secara cerdas:
  1. Jika ditemukan di tabel `warkat_codes`, memvalidasi apakah sudah pernah digunakan dan memeriksa status keaktifan kedua jalur (Charya & Pravesa). Jika valid, memunculkan menu tombol interaktif untuk memilih jalur.
  2. Jika tidak ditemukan di `warkat_codes`, fallback ke tabel `access_codes` standar.
- Pengguna dapat mengetikkan `/kode [KODE]` secara langsung (misal: `/kode WARKAT-ABC-123`) atau mengetik `/kode` terlebih dahulu lalu menempelkan kodenya.

---

## Verifikasi & Pengujian
- **Pengujian Sintaks**: Seluruh modul Python lolos kompilasi tanpa kesalahan (`python -m py_compile`).
- **Unit Testing**:
  - `tests/test_pfp.py` & `tests/test_pfp_qa.py` & `tests/test_pfp_deep.py`: Seluruh pengujian fitur PFP forward, backward range, userbot IPC fallback, budgeting, dan reward Agra lolos (36/36 tests passed).
  - `tests/test_warkat.py`: Ditambahkan 7 test case komprehensif mencakup pembuatan warkat, aksesibilitas owner, penukaran Bebas Pravesa, interaksi 3 divisi Jalur Khusus Charya, instruksi `@HRDhruvaBot`, serta persetujuan divisi pilihan ke-3 oleh admin (7/7 tests passed).
  - **Total**: 43/43 tests passed.

---

## Dokumentasi
- `docs/commands.md`: Diperbarui dengan dokumentasi `/gencode_warkat`, `/gencode_warkat_avail`, `/kode [kode]`, dan reward Agra pada `/pfp`.
- `docs/database.md`: Diperbarui dengan skema tabel `warkat_codes` dan index `idx_warkat_used_by`, `idx_warkat_created_at`.
