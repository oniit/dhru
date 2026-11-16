# Task 137: Generator Otomatis Ijazah dan Transkrip Nilai Shishya

## Ringkasan Eksekutif
Mengembangkan sistem penerbitan otomatis dokumen kelulusan shishya (Ijazah dan Transkrip Nilai) untuk Institut Dhruva Ekāgra. Sistem menghubungkan formula penilaian kurikulum Gen 1 dari spreadsheet acuan (`assets/Template IPK.xlsx`) dengan mesin generator grafis Pillow beresolusi presisi pada template resmi `assets/ijazah.png` dan `assets/transkrip.png` (552 × 777 px), serta menyediakan antarmuka Telegram untuk klaim mandiri oleh shishya dan ekspor massal oleh pengelola akademi.

---

## Latar Belakang & Analisis Penilaian
Pada Gen 1, rekapitulasi penilaian telah diselesaikan menggunakan spreadsheet perhitungan semi-manual. Bedah rumus terhadap `assets/Template IPK.xlsx` menunjukkan arsitektur kurikulum yang mapan:
1. **Beban Akademik Wajib (Total 10 SKS)**:
   - 2 Mata Kuliah Umum: `KU101` Kaidah Kebahasaan (2 SKS) & `KU102` Pengembangan Diri (2 SKS).
   - 2 Mata Kuliah Kejuruan (3 SKS/MK): Fotografi (`FG101`/`FG102`), Seni Musik (`SM101`/`SM102`), Ilmu Fisika (`IF101`/`IF102`), atau Ilmu Kimia (`IK101`/`IK102`).
2. **Pemisahan IPK vs IKK**:
   - **IPK (Indeks Prestasi Kumulatif)**: Dihitung murni dari 4 matkul akademik: $\frac{\sum (\text{SKS} \times \text{Bobot})}{10}$.
   - **IKK (Indeks Keaktifan Kumulatif)**: Dihitung terpisah dari Unit Kegiatan Mahasiswa (UKM/Klub), menjaga keaslian IPK akademik.
3. **Predikat Kelulusan**:
   - $\ge 3.51$: `CUMLAUDE`
   - $3.01 - 3.50$: `SANGAT MEMUASKAN`
   - $2.76 - 3.00$: `MEMUASKAN`
   - $2.00 - 2.75$: `CUKUP`
   - $< 2.00$: Tidak Lulus (`-`)
4. **Kriteria Kelulusan**: Shishya dengan $\text{IPK} > 2.00$ berhak dinyatakan lulus dan memperoleh Ijazah Resmi.

---

## Komponen Teknis yang Dibangun

### 1. `bot/graduation_excel.py`
Modul parser dan caching memori untuk `assets/Template IPK.xlsx`:
- Membaca sheet `bulk` dan `lulus` dengan auto-reload jika `mtime` file berubah.
- Menormalisasi format tanggal lahir (TTL) ke penanggalan formal Indonesia (contoh: `11 Mei 2010`).
- Menyediakan fungsi lookup cepat `get_student_by_nim()` dan `get_student_by_name()`.
- Mengidentifikasi 21 lulusan terverifikasi via `get_all_graduates()`.

### 2. `bot/transkrip_card.py`
Generator lembar Transkrip Nilai (552 × 777 px):
- **Pasfoto**: Slot foto $101 \times 131\text{ px}$ pada koordinat $(72, 178)$ dengan aspect-fill crop lanczos. Jika foto profil tidak tersedia, latar motif biru asli template tetap dipertahankan.
- **Identitas**: Generasi, NIM, Nama, Tanggal Lahir, Jurusan, dan Fakultas.
- **Tabel Akademik**: Grid 4 baris matkul dengan Kode, Nama, SKS, Huruf Mutu, dan Indeks Mutu.
- **Tabel UKM & Indeks**: Menampung hingga 3 klub, kalkulasi IPK, predikat kelulusan, dan nilai IKK.

### 3. `bot/ijazah_card.py`
Generator lembar Ijazah Resmi (552 × 777 px):
- **Balok Nama**: Teks putih tebal di dalam kotak navy $(67, 320, 417, 50)$ dengan mekanisme auto-shrink font jika karakter nama sangat panjang.
- **Celah Teks**: Penempatan NIM $(125, 388)$ dan Tanggal Lahir $(325, 388)$ di antara klausul penetapan rektor.
- **Predikat & Gelar**: Teks predikat tebal $(275, 445)$ dan gelar sarjana terpetakan per jurusan (misal: *Sarjana Seni Fotografi (S.Sn.)*, *Sarjana Sains Fisika (S.Si.)*).
- **Slot Foto Ijazah**: Pasfoto berukuran $132 \times 171\text{ px}$ pada koordinat $(294, 567)$.

### 4. `bot/handlers/graduation.py` & Registrasi Perintah
- `/transkrip [nim/nama]`: Mengirimkan lembar transkrip nilai ke chat privat. Mendukung lookup target oleh admin.
- `/ijazah [nim/nama]`: Memvalidasi kriteria kelulusan ($\text{IPK} > 2.00$) dan mengirimkan lembar ijazah resmi ke chat privat.
- `/export_kelulusan [zip]`: Perintah admin untuk merender seluruh dokumen lulusan Gen 1 secara batch ke direktori `output/kelulusan_gen1/` atau mengirimkannya dalam bentuk arsip ZIP.
- Proteksi keamanan: Chat privat only, rate limit per user, serta isolasi akses dokumen antar-shishya.

---

## Verifikasi & Quality Assurance (QA)
- **Render Offline Test**: Berhasil menguji render sampel (*Aluna Valencia*, *Kafka Ardhana*, dan *Lucinda Philadephia*) dengan visual 100% presisi tanpa tumpang tindih teks atau garis.
- **Batch Export Test**: Berhasil mengekspor 21 berkas transkrip dan 21 berkas ijazah (total 42 dokumen) ke folder `output/kelulusan_gen1/`.
- **Aturan QA Telegram**: Semua interaksi bot telah dikonfigurasikan agar pengujian interaktif langsung dibatasi secara eksklusif ke akun tester `TESTER_ID=1073487310`.

