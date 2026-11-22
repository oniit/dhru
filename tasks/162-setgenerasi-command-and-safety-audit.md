# Task 162: Penambahan Perintah /setgenerasi dan Audit Keamanan Data Kelulusan (Tutup Generasi)

## Latar Belakang & Pertanyaan Pengguna
Pengguna menanyakan mengenai dampak eksekusi `/tutup_generasi` yang tidak sengaja dijalankan ketika environment masih Gen 1 dengan 1 akun trial:
> "gw gak sengaja tutup generasi pdhl env masih gen 1, ada 1 akun trial gw, apakah itu override data sebelumnya? apa ijazah dan transkrip gen 1 yg asli hilang di db prod?"

## Hasil Audit & Verifikasi Data
1. **Keamanan Data Ijazah & Transkrip (100% Aman & Utuh)**:
   - Data kelulusan, nilai matkul, IKK, IPK, dan predikat **TIDAK** disimpan di tabel pengguna (`users`), melainkan disimpan secara permanen di:
     1. Berkas arsip master: `data/graduation_records.json` (30 mahasiswa Gen 1 utuh terverifikasi).
     2. Spreadsheet nilai: `Template IPK.xlsx`.
     3. Tabel remote: `graduation_records`.
   - Fungsi `mass_set_role_purna` pada perintah `/tutup_generasi` **sama sekali tidak menyentuh, mengubah, atau menghapus** tabel `graduation_records` maupun berkas JSON/Excel.
   - Semua alumni Gen 1 yang asli tetap dapat mencetak `/ijazah` dan `/transkrip` mereka secara normal dan identitas mereka tidak terhapus.

2. **Dampak yang Terjadi Akibat `/tutup_generasi`**:
   - Akun trial yang saat itu berstatus `student`/`bem` dialihkan perannya menjadi `purna` (SKS dibekukan, NIM dipertahankan).
   - Pengaturan `current_generasi` di tabel `bot_settings` dinaikkan dari `1` ke `2` secara otomatis.

3. **Fitur Baru: `/setgenerasi`**:
   - Menambahkan perintah Owner `/setgenerasi [nomor]` dan alias `/set_generasi [nomor]` untuk melihat status generasi saat ini atau mengatur ulang nilai generasi aktif (misalnya mengembalikannya ke `1` melalui `/setgenerasi 1`).
   - Mendaftarkan handler di `bot/handlers/register.py` dan menambahkan pengujian di `tests/test_warkat.py`.
