# Task 147: Normalisasi Awalan Angka Nol (Leading Zero) pada Format NIM Kelulusan

## Ringkasan Eksekutif
Menemukan dan memperbaiki inkonsistensi format NIM antara file spreadsheet Excel (`Template IPK.xlsx`) dengan remote database Turso di lingkungan *Production*. Di database Production, seluruh 21 mahasiswa kelulusan Gen 1 tersimpan dengan format resmi **11 digit** (menggunakan awalan 2 digit kode fakultas `01` atau `02`, contoh: `02004010093`). Namun, program Excel menyimpan data NIM sebagai angka numerik sehingga memotong angka nol di depan menjadi **10 digit** (contoh: `2004010093`). Hal ini menyebabkan kueri pencarian foto menghasilkan `0 / 21`.

Dengan normalisasi dua arah (*bidirectional padding/unpadding*), sistem kini secara otomatis mengenali dan mencocokkan baik format 10 digit maupun 11 digit resmi, sehingga seluruh **21 dari 21 foto mahasiswa** di Production berhasil ditemukan dan ditempelkan ke dokumen kelulusan.

---

## Rincian Perubahan Teknis
1. **Normalisasi Data Spreadsheet (`bot/graduation_excel.py`)**:
   - Jika nilai NIM dari cell Excel berupa angka 10 digit, otomatis distandarisasi ke format 11 digit resmi Dhruva via `.zfill(11)` (contoh: `2004010093` -> `02004010093`).
   - `data_map` internal memetakan kunci pencarian baik dalam bentuk 11 digit maupun 10 digit (`.lstrip("0")`).
   - Fungsi `get_student_by_nim()` kini mendukung input dalam format 10-digit, 11-digit, maupun tipe integer, sehingga perintah `/transkrip <nim>` dan `/ijazah <nim>` bekerja fleksibel.
   - Fungsi `get_all_graduates()` dan `get_all_students()` dilengkapi mekanisme deduplikasi agar selalu mengembalikan tepat 21 lulusan unik.
2. **Kueri Multivariasi Foto Kelulusan (`bot/handlers/graduation.py`)**:
   - Pada `_fetch_photos_for_graduates()`, himpunan kandidat NIM yang dicari via SQL `WHERE student_id IN (...)` menyertakan variasi format (`nim`, `nim.zfill(11)`, `nim.lstrip("0")`), menjaga efisiensi kueri terindeks `idx_users_student_id`.
   - `student_map` memetakan foto ke seluruh variasi format NIM sehingga pencocokan foto dengan objek mahasiswa berjalan instan.
   - Pada `_get_photo_bytes_for_student()`, kueri pencarian tunggal juga mendukung variasi kandidat NIM tersebut.
3. **Pembaruan Versi Cache Kartu**:
   - Menaikkan `_LAYOUT_VERSION = 7` pada `bot/ijazah_card.py` dan `bot/transkrip_card.py` untuk memastikan dokumen di-render dengan format NIM 11 digit terbaru.

---

## Verifikasi
- Pengujian kueri terhadap database Production membuktikan bahwa dengan pencocokan multivariasi `zfill(11)`, sebanyak **21 dari 21 mahasiswa (100%)** memiliki baris yang cocok dan memiliki pasfoto di database Production.
- Batch test terhadap seluruh 21 lulusan berhasil 100% dan verifikasi visual pada ijazah maupun transkrip mengonfirmasi NIM 11 digit tertata rapi dan proporsional.

