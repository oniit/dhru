# Unifikasi Perintah ID Card & Pas Foto

## Latar Belakang
Pengguna merasa perintah `/kts`, `/kts_foto`, `/kic`, dan `/kic_foto` terlalu membingungkan dan meminta agar semuanya disatukan menjadi `/kartu` (untuk menampilkan kartu) dan perintah tunggal untuk mengatur foto.

## Apa yang Dikerjakan
1. **Migrasi Database**: 
   - Dibuat script migrasi `migrate_photos.py` untuk membaca JSON profil setiap user di database.
   - Script mengambil *file id* foto dari *key* lama (`kts_photo_file_id` dan `kic_photo_file_id`), memindahkannya ke *key* tunggal `photo_file_id`.
   - *Key* lama dihapus sehingga *database* menjadi bersih tanpa *double data*.
2. **Pembuatan File Handler Baru (`bot/handlers/kartu.py`)**:
   - Menyatukan logika pembuatan kartu ID.
   - Perintah `/kartu`: mengecek role pengguna. Jika mahasiswa, panggil `render_kts_png_bytes`. Jika internal/staf, panggil `render_kic_png_bytes`.
   - Perintah `/foto`: menerima masukan foto dari user dan menyimpannya langsung ke *key* `photo_file_id` dalam *database*.
3. **Pembersihan Logika Lama**:
   - Menghapus file `bot/handlers/kts.py` dan `bot/handlers/kic.py`.
   - Memperbarui `bot/handlers/register.py` dan `bot/handlers/messages.py` untuk menggunakan *handler* dari `kartu.py`.
4. **Pembaruan Ekspor Foto & Teks Bantuan**:
   - Perintah `/export_photos` diubah agar hanya mencari kunci `photo_file_id`. Output dalam ZIP akan otomatis disortir ke folder `KTS/` atau `KIC/` berdasarkan `role` *user*.
   - Mengubah teks bantuan `/help` di dalam `commands.py` untuk mendokumentasikan `/kartu` dan `/foto`.
5. **Pembaruan Dokumentasi**:
   - Memperbarui daftar perintah di `docs/commands.md`.

## Alur Kode Secara Teknis
- *Handler* utama berada di `bot/handlers/kartu.py`.
- Ketika user memanggil `/kartu`, kode akan membaca parameter `role` pada baris pengguna dari tabel `users`.
- Jika `ROLE_INTERNAL`, maka bot menjalankan `bot.kic_card.render_kic_png_bytes`.
- Jika `ROLE_STUDENT` atau `ROLE_BEM`, bot menjalankan `bot.kts_card.render_kts_png_bytes`.
- Jika pengguna mengirim foto melalui `/foto`, `onboarding_step` akan diatur ke `STEP_KARTU_PHOTO`.
- Foto akan ditangkap oleh fungsi `on_foto` di `kartu.py` (yang terhubung melalui *hook* `on_private_photo` di `messages.py`), kemudian disimpan ke profil JSON dengan atribut `photo_file_id`.
