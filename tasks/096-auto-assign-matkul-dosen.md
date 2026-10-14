# Task 096: Optimasi Role Dosen & Penyederhanaan Charyarthi

## Deskripsi Singkat
Pada pembaruan ini, dilakukan penyederhanaan fitur pendaftaran calon staf (Charyarthi) menjadi 1 pilihan divisi saja (sebelumnya ada opsi divisi cadangan). Selain itu, sistem Dosen dirombak agar tidak perlu lagi memilih seluruh mata kuliah secara manual satu per satu, melainkan ditarik otomatis dari 'Homebase Jurusan' (Jurusan yang diajarkan).

## Detail Pekerjaan
1. **Penyederhanaan Registrasi Charyarthi (`commands.py`):**
   - Menghapus logika pemilihan divisi kedua (`target_division_2`).
   - Menambahkan pesan peringkasan yang sangat jelas pada `/settings_charyarthi` setelah admin menekan tombol "Tutup/Selesai" untuk menghindari kebingungan status pendaftaran.
   - UI diringkas sehingga tombol 'Divisi Pilihan 2' disembunyikan.

2. **Sistem Auto-Assign Mata Kuliah Dosen (`profile_fields.yaml` & `common.py`):**
   - Menambahkan *field* baru bernama `staff_major` khusus untuk peran Dosen.
   - *Field* ini memfilter daftar jurusan (`majors`) berdasarkan fakultas (`staff_faculty`) yang dipilih Dosen.
   - Pada file `bot/handlers/common.py` fungsi `lecturer_class_ids`, ditambahkan sebuah _loop_ yang otomatis memberikan akses presensi untuk seluruh kelas (matkul) yang ada di bawah naungan `staff_major` pilihan dosen bersangkutan.
   - Pemilihan mata kuliah secara manual (lintas jurusan) lewat `teaching_classes` tetap dipertahankan.
   - Guru Besar secara fungsional tetap mengandalkan `teaching_classes` secara manual agar tidak tumpang tindih.

## Status QA
- [x] Tested: Profile `staff_major` tersimpan di JSON database.
- [x] Tested: Opsi Charyarthi divisi kedua dihapus dan langsung melompat ke submit.
- [x] Laporan ini sudah ter-record secara sekuensial.
