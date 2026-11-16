# Task 143: Penyesuaian Warna Font #13325B, Penyelarasan Layout Ijazah, dan Formatting Bold Transkrip

## Ringkasan Eksekutif
Menyesuaikan warna seluruh teks pada dokumen Ijazah dan Transkrip Nilai ke kode warna hex **`#13325B`** (`RGB: 19, 50, 91`), menaikkan posisi NIM dan Tanggal Lahir pada ijazah sebesar 2px ($Y=388$), menambahkan kata "Fakultas" serta mem-bold teks *Jurusan - Fakultas*, memperbesar dan mem-bold gelar akademik resmi (18px), serta menerapkan pemformatan tebal (*bold*) pada Generasi/NIM, Nama, IPK, IKK, dan Predikat Kelulusan pada transkrip nilai dengan auto-shrink untuk mencegah teks *"SANGAT MEMUASKAN"* melebar menabrak garis tepi tabel.

---

## Rincian Perubahan Teknis

### 1. `bot/ijazah_card.py`
- Mengubah konstanta warna teks menjadi `NAVY = (19, 50, 91, 255)` (`#13325B`).
- Menaikkan posisi vertikal baris NIM dan Tanggal Lahir dari $Y=390$ menjadi $Y=388$ (naik 2 px).
- Format Jurusan dan Fakultas: menambahkan awalan `"Fakultas "` di depan nama fakultas jika belum ada, serta menerapkan *stroke bold* (`stroke_width=0.4`) pada font Open Serif ukuran 16px.
- Format Gelar Akademik resmi: diperbesar dari ukuran 15px menjadi 18px dengan *stroke bold* (`stroke_width=0.4`) pada font Open Serif.
- Meningkatkan versi cache `_LAYOUT_VERSION = 5`.

### 2. `bot/transkrip_card.py`
- Mengubah konstanta warna teks menjadi `NAVY = (19, 50, 91, 255)` (`#13325B`).
- Menjadikan baris Generasi/NIM dan Nama Mahasiswa berformat tebal (*bold* via `stroke_width=0.4`), sedangkan Tanggal Lahir, Jurusan, dan Fakultas tetap menggunakan format reguler.
- Menjadikan teks nilai IPK dan IKK berformat tebal (*bold*).
- Menjadikan Predikat Kelulusan berformat tebal (*bold*) dengan mekanisme auto-shrink adaptif:
  - Lebar kotak nilai predikat pada template adalah 141 px ($X=351$ hingga $X=492$).
  - Predikat `"CUMLAUDE"` berukuran 13px ($w \approx 75\text{ px}$).
  - Predikat panjang `"SANGAT MEMUASKAN"` secara otomatis di-shrink ke 11px ($w \approx 110\text{ px}$) sehingga memiliki margin aman $\approx 15\text{ px}$ di kiri dan kanan tanpa menabrak garis tepi template.
- Meningkatkan versi cache `_LAYOUT_VERSION = 5`.

---

## Verifikasi
- Pengujian rendering terhadap mahasiswa predikat *CUMLAUDE* (*Aluna Valencia*) dan mahasiswa predikat *SANGAT MEMUASKAN* (*Lucinda Philadephia*) berhasil diverifikasi dengan layout proporsional.
- Verifikasi visual memastikan warna font `#13325B` selaras dengan border template, baseline NIM/TTL seimbang, serta teks gelar tampil lebih mencolok dan formal.

