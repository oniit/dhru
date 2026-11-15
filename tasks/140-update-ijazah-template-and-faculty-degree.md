# Task 140: Penyesuaian Template Ijazah Baru, Center Tanggal Lahir & NIM, serta Pemetaan Gelar Fakultas

## Ringkasan Eksekutif
Menyesuaikan generator Ijazah Kelulusan (`bot/ijazah_card.py` dan `bot/handlers/graduation.py`) terhadap template grafis terbaru `assets/ijazah.png`:
1. Mengubah format isian ijazah dari yang sebelumnya menampilkan predikat kelulusan menjadi **"Jurusan - Fakultas"** (contoh: *Fotografi - Ilmu Budaya*, *Ilmu Fisika - Matematika dan IPA*).
2. Memperbarui pemetaan gelar akademik resmi berdasarkan fakultas shishya:
   - **Fakultas Matematika dan IPA (FMIPA)**: `Sarjana Sains (S.Si.)`
   - **Fakultas Ilmu Budaya (FIB)**: `Sarjana Seni (S.Sn.)`
3. Memposisikan teks **Tanggal Lahir** dan **NIM** di tengah (*center align*) masing-masing celah kosong template pada baris $Y=390$ dengan koordinat horizontal presisi (NIM di $X=156$, TTL di $X=392$), sehingga jarak kosong kiri dan kanan seimbang rapi.
4. Memastikan seluruh tipografi menggunakan font **Mukta** (`Mukta-Bold.ttf`, `Mukta-SemiBold.ttf`, `Mukta-Medium.ttf`, `Mukta-Regular.ttf`).
5. Melakukan evaluasi teknis terkait *remove background* pasfoto: Tidak diterapkan karena memerlukan model AI eksternal (~170MB), beban komputasi CPU berat, dan risiko ketidaksesuaian visual dengan tekstur biru slot pasfoto template. Pemotongan rapi berbasis rasio pasfoto resmi ($3 \times 4$ aspect fill) dipertahankan.

---

## Rincian Perubahan Teknis

### 1. `bot/ijazah_card.py`
- Menghapus ketergantungan pada label predikat kelulusan di dalam gambar ijazah.
- Mengganti teks di bawah "serta dinyatakan lulus dari:" ($Y=447$) dengan `f"{student.jurusan} - {student.fakultas}"` menggunakan font `Mukta-Bold` 15px warna navy (`#132743`).
- Mengubah fungsi `get_degree_title(fakultas, jurusan)`:
  - Fakultas FIB / Jurusan Fotografi & Musik $\rightarrow$ `Sarjana Seni (S.Sn.)`
  - Fakultas FMIPA / Jurusan Kimia & Fisika $\rightarrow$ `Sarjana Sains (S.Si.)`
  - Dirender pada $Y=502$ menggunakan font `Mukta-SemiBold` 15px.
- Mengatur alignment `NIM` ($X=156, Y=390$) dan `Tanggal Lahir` ($X=392, Y=390$) dengan `anchor="mm"` menggunakan font `Mukta-SemiBold` 11px.
- Meningkatkan `_LAYOUT_VERSION = 2` untuk invalidasi cache lama.

### 2. `bot/transkrip_card.py`
- Menambahkan referensi `FONT_MEDIUM_PATH` dari `assets/Mukta/Mukta-Medium.ttf`.
- Meningkatkan `_LAYOUT_VERSION = 2`.

### 3. `bot/handlers/graduation.py`
- Mengimpor `get_degree_title` dari `bot.ijazah_card`.
- Memperbarui caption Telegram pada `cmd_ijazah` untuk menampilkan nama, NIM, Program Studi - Fakultas, dan Gelar Akademik resmi.

---

## Verifikasi
- Pengujian rendering terhadap mahasiswa FIB (*Aluna Valencia*) menghasilkan gelar *Sarjana Seni (S.Sn.)* dan teks *Fotografi - Ilmu Budaya*.
- Pengujian rendering terhadap mahasiswa FMIPA (*Aethel Chi Solaine*) menghasilkan gelar *Sarjana Sains (S.Si.)* dan teks *Ilmu Fisika - Matematika dan IPA*.
- Posisi tanggal lahir dan NIM telah terverifikasi secara visual sejajar baseline dan terpusat rata di antara teks template bawaan.
- Seluruh 21 mahasiswa lulusan berhasil di-render tanpa eror.

