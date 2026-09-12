# Task 075: Perbaikan Command Status Kata Rahasia

## Deskripsi
Memperbaiki bug pada perintah `/status kata_rahasia` yang tidak merespon, serta menambahkan fitur baru untuk menampilkan daftar kata rahasia yang telah berhasil ditebak sejauh ini.

## Detail Pengerjaan
1. **Perbaikan Parsing Mode Markdown:**
   - Masalah awal: `parse_mode="Markdown"` menyebabkan error diam (silent error) saat mencetak variabel yang berisi karakter khusus (misalnya `_` pada nama setting atau nama user).
   - Solusi: Mengubah format pesan di fungsi `mulai_kata_rahasia`, `status_kata_rahasia`, `berhenti_kata_rahasia`, dan `hasil_kata_rahasia` menjadi `HTML`.
   - Menggunakan `html.escape()` untuk menghindari error formatting dari input user.

2. **Fitur Menampilkan Kata Ditebak:**
   - Menyimpan `found_words` ke dalam state game di list `claimed_words` pada setiap respon yang berhasil.
   - Mengubah output dari `status_kata_rahasia` untuk menampilkan bagian "Telah ditebak" yang memperlihatkan daftar kata yang sudah ditemukan.
