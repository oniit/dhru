# Task 142: Pembaruan Font Nama Ijazah Menjadi Cinzel Bold

## Ringkasan Eksekutif
Mengubah konfigurasi font nama mahasiswa pada Ijazah Kelulusan (`bot/ijazah_card.py`) dari yang sebelumnya menggunakan Mukta Bold menjadi **Cinzel Bold** (`assets/Cinzel/Cinzel-Bold.otf`). Teks isi lainnya pada ijazah dan transkrip tetap menggunakan **Open Serif** (`assets/Open_Serif/OpenSerif-Book.ttf`).

---

## Rincian Perubahan Teknis
- Mengarahkan `FONT_CINZEL_BOLD_PATH = ROOT / "assets" / "Cinzel" / "Cinzel-Bold.otf"`.
- Nama mahasiswa di kotak biru ijazah dirender menggunakan font Cinzel Bold dengan ukuran awal 20px, warna putih, terpusat di $(276, 345)$, dengan auto-shrink jika lebar nama $>390\text{ px}$.
- Meningkatkan versi cache `_LAYOUT_VERSION = 4` untuk invalidasi cache gambar lama.

---

## Verifikasi
- Pengujian rendering grafis seluruh 21 mahasiswa lulusan Gen 1 berjalan sukses 100%.
- Nama-nama panjang (seperti *Zeivalle Aravie Nyxaria*, *Jaganatha Damar Prasodjo*, *Sabiru Anantara Nalendra*) muat dengan presisi di dalam kotak banner biru tua tanpa tumpang tindih.

