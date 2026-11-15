# Task 144: Penerapan Font Cinzel Bold pada Jurusan-Fakultas dan Gelar Akademik Ijazah

## Ringkasan Eksekutif
Mengubah tipografi teks **Jurusan - Fakultas** dan **Gelar Akademik** pada Ijazah Kelulusan (`bot/ijazah_card.py`) ke font **Cinzel Bold** (`assets/Cinzel/Cinzel-Bold.otf`), selaras dengan font nama shishya di banner biru. Teks NIM dan Tanggal Lahir tetap menggunakan font **Open Serif** agar menyatu alami dengan kalimat pembuka ijazah.

---

## Rincian Perubahan Teknis
- Mengarahkan render teks `Jurusan - Fakultas` di $(276, 447)$ menggunakan font `Cinzel-Bold.otf` ukuran 15px (warna navy `#13325B`), dilengkapi pengaman auto-shrink jika lebar baris melebihi 420px.
- Mengarahkan render teks `Gelar Akademik Resmi` di $(276, 502)$ menggunakan font `Cinzel-Bold.otf` ukuran 16px (warna navy `#13325B`).
- Meningkatkan versi cache `_LAYOUT_VERSION = 6` untuk invalidasi instan terhadap cache sebelumnya.

---

## Verifikasi
- Pengujian rendering visual terhadap mahasiswa FIB (*Aluna Valencia*) dan mahasiswa FMIPA (*Aethel Chi Solaine*) menghasilkan tampilan klasik roman serif yang sangat berwibawa dan serasi dengan judul sertifikat.
- Batch test terhadap seluruh 21 mahasiswa lulusan Gen 1 berhasil 100% tanpa ada teks yang terpotong.

