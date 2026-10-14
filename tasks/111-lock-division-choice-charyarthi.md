# 111 - Lock Division Choice During Chāryārthī Quiz

## Ringkasan
Menambahkan langkah konfirmasi saat calon staf (Chāryārthī) memilih divisi sebelum mengerjakan soal tes, dan menghapus tombol "Ganti Pilihan Divisi" dari dashboard soal agar pendaftar tidak bisa mengganti divisi setelah dikonfirmasi.

## Alasan
Sebelumnya, pendaftar bisa mengganti divisi kapan saja selama proses pengisian soal tes. Ini berpotensi menyebabkan data jawaban yang tidak konsisten. Perubahan ini memastikan pendaftar benar-benar yakin dengan pilihan divisinya sebelum mulai mengerjakan soal.

## Perubahan Teknis

### `bot/handlers/commands.py`
- **`charyarthi:div1` handler**: Diubah dari langsung menyimpan divisi ke menampilkan halaman konfirmasi dengan pesan peringatan bahwa divisi tidak bisa diganti. Disertai link ke @dhruvarsip untuk mengecek jobdesc.
- **`charyarthi:confirm_div1` handler** (baru): Handler baru yang menjalankan logika penyimpanan divisi dan lanjut ke soal/form, yang sebelumnya ada di `div1` handler.
- **`charyarthi:reselect` handler**: Tetap ada tetapi sekarang hanya bisa diakses dari halaman konfirmasi (tombol "🔙 Pilih Divisi Lain"), bukan dari dashboard soal.

### `bot/handlers/common.py`
- **`render_charyarthi_quiz_view()`**: Menghapus tombol "🔄 Ganti Pilihan Divisi" (`charyarthi:reselect`) dari dashboard soal.

## Alur Baru
1. Pendaftar memilih divisi → muncul halaman konfirmasi
2. Halaman konfirmasi berisi: nama divisi, peringatan tidak bisa ganti, link @dhruvarsip, dan 3 tombol:
   - ✅ Ya, Saya Yakin Pilih [Divisi]
   - 🔙 Pilih Divisi Lain
   - ❌ Batal Pendaftaran
3. Jika dikonfirmasi → divisi disimpan dan lanjut ke soal/form (seperti sebelumnya)
4. Selama mengerjakan soal, tidak ada opsi untuk mengganti divisi
