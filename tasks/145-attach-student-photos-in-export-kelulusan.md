# Task 145: Integrasi Pasfoto Mahasiswa ke Fitur Batch Export Kelulusan

## Ringkasan Eksekutif
Mengintegrasikan pengambilan dan penempelan pasfoto mahasiswa secara otomatis pada perintah massal `/export_kelulusan [zip]`. Sebelumnya, proses ekspor batch hanya me-render data teks tanpa menyertakan foto (`photo_bytes=None`). Kini, sistem mengunduh pasfoto resmi KTS (`photo_file_id`) atau avatar Telegram mahasiswa secara paralel dan hemat kuota Turso sebelum di-render ke dalam dokumen Ijazah dan Transkrip Nilai.

---

## Rincian Perubahan Teknis
1. **Pengambilan Foto Paralel & Perlindungan Kuota Turso (`bot/handlers/graduation.py`)**:
   - Menambahkan fungsi asinkron `_fetch_photos_for_graduates(context, conn, graduates)`.
   - Melakukan batch query ke tabel `users` dengan memanfaatkan index fungsional `idx_users_student_id` menggunakan klausa `WHERE json_extract(profile_json, '$.student_id') IN (...)`, membatasi read quota Turso hanya pada baris mahasiswa yang relevan.
   - Mengunduh pasfoto resmi KTS (`photo_file_id`) atau fallback ke avatar profil Telegram (`get_user_profile_photos`) secara paralel dengan kontrol konkurensi `asyncio.Semaphore(5)` guna menghindari rate limit Telegram API (*FloodWait*).
2. **Penyisipan Foto ke Pipeline Rendering Batch**:
   - Memperbarui fungsi CPU-bound `_sync_export_documents` agar menerima parameter `photos_map: dict[str, bytes | None] | None = None`.
   - Meneruskan `photo_bytes = photos_map.get(st.nim)` ke `render_transkrip_png_bytes` dan `render_ijazah_png_bytes`.
   - Menyediakan fallback aman (*graceful fallback*): mahasiswa yang belum memasang foto atau belum terdaftar tetap diekspor tanpa error dengan slot foto kosong.
3. **Peningkatan UX Admin**:
   - Notifikasi progres di chat menginformasikan jumlah foto yang berhasil ditemukan (contoh: `Foto ditemukan: X / 21`).
   - Rangkuman pesan akhir dan keterangan file ZIP diperbarui untuk mencantumkan status dokumen berfoto.
4. **Pembaruan Dokumentasi**:
   - Memperbarui `docs/commands.md` pada deskripsi `/export_kelulusan`.

---

## Verifikasi
- Pengujian unit test CPU-bound pada `_sync_export_documents` menggunakan simulasi data gambar JPEG lulus 100% dan menghasilkan dokumen ijazah & transkrip dengan ukuran file valid (>50KB).
- Pemeriksaan sintaksis dan impor modul berjalan tanpa error.

