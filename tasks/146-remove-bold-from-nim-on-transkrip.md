# Task 146: Menghapus Efek Bold pada Generasi dan NIM di Transkrip Nilai

## Ringkasan Eksekutif
Menyesuaikan tipografi pada kartu Transkrip Nilai (`bot/transkrip_card.py`) dengan menghapus ketebalan teks (*simulated stroke bold*) pada baris **Generasi / NIM** (`f"{student.generasi} / {student.nim}"`). Teks kini menggunakan bobot standar (*regular weight*) dari font **Open Serif**, senada dengan baris Tanggal Lahir, Jurusan, dan Fakultas, sementara **Nama Mahasiswa** tetap dipertahankan dengan format **Bold**.

---

## Rincian Perubahan Teknis
- Menghapus atribut `stroke_width=0.4` dan `stroke_fill=NAVY` pada pemanggilan `draw.text((325, 204), f"{student.generasi} / {student.nim}", fill=NAVY, font=font_open_12)`.
- Menaikkan versi cache layout `_LAYOUT_VERSION = 6` pada `bot/transkrip_card.py` agar invalidasi cache gambar transkrip berjalan otomatis.

---

## Verifikasi
- Pengujian visual pada [scratch/sample_transkrip_unbold_nim.png](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/scratch/sample_transkrip_unbold_nim.png) mengonfirmasi baris Generasi / NIM tampil dengan ketebalan proporsional (regular), serasi dengan data identitas di bawahnya.
- Batch test pada seluruh 21 mahasiswa kelulusan Gen 1 lolos 100%.

