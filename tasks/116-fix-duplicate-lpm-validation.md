# Task 116: Pencegahan Validasi Duplikat Link LPM & Story

## Latar Belakang Masalah
Pengguna melaporkan adanya masalah validasi tautan promosi LPM yang terproses ganda (*"validasi link lpm kedouble"*). Hal ini mengakibatkan:
1. Pengguna menerima dua respons bersamaan (edit pesan langsung dari perintah `/lpm` dan notifikasi pesan pribadi terpisah dari background worker).
2. Terjadi pemberian poin ganda (+2 Agra alih-alih +1 Agra) untuk satu tautan promosi yang sama.
3. Potensi klaim ganda menggunakan variasi penulisan URL Telegram (misal penambahan parameter `?single`, garis miring penutup `/`, atau kombinasi huruf besar-kecil pada username).

---

## Analisis Masalah Holistik & Akar Masalah (*Root Causes*)
1. **Race Condition antara Foreground & Background Worker**:
   - Saat pengguna menjalankan perintah `/lpm <link>`, handler `lpm_cmd` langsung memasukkan tautan ke tabel `promo_verifications` dengan status default `PENDING`.
   - Handler kemudian mengeksekusi fungsi asinkron `verify_lpm_link_embed` yang memerlukan waktu 1–3 detik untuk scraping HTTP Telegram embed.
   - Bersamaan dengan itu, job queue berkala `process_promo_queue` di `bot/jobs.py` (yang berjalan setiap 10 detik) dan loop `checker.py` mengambil antrean dengan query `SELECT * FROM promo_verifications WHERE status = 'PENDING'`.
   - Jika background queue melakukan *tick* saat pemeriksaan foreground sedang berlangsung, kedua worker sama-sama membaca status `PENDING`, sama-sama berhasil memvalidasi embed, sama-sama mengubah status menjadi `VALID`, dan keduanya memberikan +1 Agra (`db.add_agra`) serta mengirim pesan sukses ke pengguna.
2. **Ketiadaan Kanonisasi Tautan (URL Canonicalization)**:
   - Tautan disimpan mentah (*raw string*) sebagaimana diketik pengguna.
   - Pengecekan duplikasi `SELECT * FROM promo_verifications WHERE link = ?` hanya mencocokkan string secara eksak. Tautan seperti `https://t.me/grup/123?single` dan `https://t.me/Grup/123` dianggap berbeda sehingga lolos dari deteksi tautan yang sudah pernah diklaim.
3. **Double Submission / Klik Beruntun**:
   - Sebelum perbaikan, pengecekan awal di `lpm_cmd` hanya memeriksa `rec["status"] == "VALID"`. Jika pengguna mengirim perintah berkali-kali secara cepat, status tautan masih `PENDING` sehingga lolos pengecekan berulang.

---

## Solusi & Implementasi Teknis

### 1. Kanonisasi Format URL Telegram (`bot/handlers/promo.py`)
- Menambahkan fungsi helper `normalize_telegram_post_link(link: str) -> str | None`:
  - Mengabaikan perbedaan huruf kapital/kecil pada username kanal/grup.
  - Membuang parameter query string seperti `?single`, `?comment=...`, `?embed=1`.
  - Membuang *trailing slash*.
  - Mengubah ke format standar kanonikal: `https://t.me/<username_lowercase>/<msg_id>` (atau `https://t.me/c/<id>/<id>` untuk grup privat).
- Menambahkan helper `normalize_telegram_story_link(link: str) -> str | None` untuk menstandarkan tautan format Story: `https://t.me/<username_lowercase>/s/<story_id>`.

### 2. Pencegahan Submit Tautan Sedang Diproses (In-Flight / Double-Click Lock)
- Pada `lpm_cmd` dan `story_cmd`, pengecekan riwayat tautan diperluas:
  - Jika tautan sudah `VALID`, tolak: *"Link promosi ini sudah pernah divalidasi dan diklaim sebelumnya."*
  - Jika tautan berstatus `PENDING` atau `PROCESSING`, tolak: *"Link promosi ini sedang dalam antrean atau proses validasi. Mohon tunggu beberapa saat dan tidak mengirim ulang berkali-kali."*

### 3. Penguncian Status Transisi Atomik (`PROCESSING`)
- **Foreground (`lpm_cmd`)**:
  - Menyimpan verifikasi baru langsung dengan status `PROCESSING` (`db.add_promo_verification(..., status='PROCESSING')`), sehingga background worker yang mencari `WHERE status = 'PENDING'` tidak akan mengambil tautan yang sedang diperiksa di foreground.
  - Pengesahan status `VALID` dilakukan secara kondisional:
    `UPDATE promo_verifications SET status = 'VALID' WHERE id = ? AND status = 'PROCESSING'`
    Poin Agra hanya diberikan jika `rowcount > 0` (hanya jika worker ini yang berhasil mengubah status).
  - Jika terjadi kendala jaringan (`NETWORK_ERROR`), status secara aman di-downgrade menjadi `PENDING` agar background queue dapat mencoba ulang.
- **Background Job (`bot/jobs.py` & `checker.py`)**:
  - Sebelum memproses item dari antrean `PENDING`, worker menjalankan *atomic claim*:
    `UPDATE promo_verifications SET status = 'PROCESSING' WHERE id = ? AND status = 'PENDING'`
    Hanya baris yang berhasil diubah (`rowcount > 0`) yang akan dievaluasi dan diberi reward.
  - Saat terjadi FloodWait atau error sementara, status dikembalikan ke `PENDING`.
- **Database Helper (`bot/database.py`)**:
  - `add_promo_verification` diperbarui agar menerima parameter `status` (default `'PENDING'`, bisa diset `'PROCESSING'`) dan menjaga integritas tautan yang sudah berstatus `VALID` agar tidak di-overwrite kembali menjadi `PENDING`.

---

## Verifikasi & Pengujian
Pengujian komprehensif di `tests/test_promo_lpm.py` mencakup:
1. `test_verify_lpm_link_embed_real_link`: Verifikasi scraping embed tautan publik, deteksi kata kunci salah, dan ketidaksesuaian pengirim.
2. `test_lpm_cmd_interactive_responses`: Verifikasi respons instan pesan tunggu dan edit otomatis menjadi status sukses.
3. `test_normalize_telegram_post_and_story_links`: Memverifikasi normalisasi URL (casing, query params, trailing slashes, private formats, story formats).
4. `test_lpm_cmd_blocks_duplicates_and_variations`: Memverifikasi pemblokiran duplikasi baik dengan URL varian (`?single`), URL yang sudah `VALID`, maupun tautan yang sedang `PROCESSING` / `PENDING`.
5. `test_promo_queue_atomic_locking`: Memverifikasi bahwa `process_promo_queue` tidak menyentuh atau menduplikasi reward untuk tautan yang sedang diproses (`PROCESSING`) oleh foreground.

Hasil seluruh tes: **100% Passed** (5 test cases di `test_promo_lpm.py` dan seluruh suite kontrak tanpa regresi).
