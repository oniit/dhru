# Task 141: Penerapan Tipografi Open Serif pada Transkrip & Ijazah serta Mukta Bold untuk Nama Ijazah

## Ringkasan Eksekutif
Mengganti seluruh konfigurasi tipografi teks isi pada dokumen Ijazah dan Transkrip Nilai (`bot/transkrip_card.py` dan `bot/ijazah_card.py`) ke font **Open Serif** (`assets/Open_Serif/OpenSerif-Book.ttf`), serta menggunakan font **Mukta Bold** (`assets/Mukta/Mukta-Bold.ttf`) khusus untuk nama shishya di dalam kotak banner biru ijazah.

---

## Rincian Perubahan Teknis

### 1. `bot/transkrip_card.py`
- Mengganti sumber font ke `FONT_OPEN_SERIF_PATH = ROOT / "assets" / "Open_Serif" / "OpenSerif-Book.ttf"`.
- Menyesuaikan penempatan teks identitas mahasiswa pada X=325 seiring template baru yang telah menghapus label kata "Generasi" setelah tanda titik dua (`:`).
- Menggunakan ukuran:
  - Identitas (NIM, Nama, TTL, Prodi, Fakultas): 12px (dengan auto-shrink jika nama panjang > 160px).
  - Baris Tabel Mata Kuliah: Kode (10px), Nama MK (10px), SKS (10px), Nilai (11px), Indeks (10px).
  - Nilai IPK: 11px; Predikat: 13px.
  - Baris Tabel UKM: Nama UKM (10px), SKS (10px), Nilai (11px).
  - Nilai IKK: 11px.
- Meningkatkan versi cache `_LAYOUT_VERSION = 3`.

### 2. `bot/ijazah_card.py`
- Nama Mahasiswa di kotak biru ijazah menggunakan `Mukta-Bold.ttf` 20px (font putih, terpusat horizontal di $(276, 345)$, auto-shrink jika lebar > 390px).
- NIM dan Tanggal Lahir menggunakan `OpenSerif-Book.ttf` 11px, terpusat rapi di masing-masing celah baris $Y=390$ template bawaan ($X=156$ untuk NIM, $X=392$ untuk Tanggal Lahir).
- Teks *Jurusan - Fakultas* menggunakan `OpenSerif-Book.ttf` 16px di $(276, 447)$.
- Teks Gelar Akademik resmi menggunakan `OpenSerif-Book.ttf` 15px di $(276, 502)$.
- Meningkatkan versi cache `_LAYOUT_VERSION = 3`.

---

## Verifikasi
- Pengujian rendering grafis dokumen Ijazah dan Transkrip berjalan sempurna tanpa galat.
- Tipografi Open Serif menyatu alami dengan teks cetak bawaan template, dan nama di ijazah tampak tegas dan kontras menggunakan Mukta Bold.

