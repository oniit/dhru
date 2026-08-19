# 032: LPM Checker & Userbot Integration

## Deskripsi Tugas
Menambahkan fitur agar Maba dan pengguna internal dapat mensubmit link pesan promosi (LPM) dari grup publik untuk mendapatkan reward Agra secara otomatis. Karena keterbatasan Telegram Bot API yang tidak dapat membaca isi pesan dari grup asing, kita menggunakan pendekatan *Microservice* dengan dua script terpisah:
1. `main.py` (Bot Telegram Standar): Menerima link dari user.
2. `checker.py` (Pyrogram Userbot): Berjalan di background, membaca pesan di grup publik, memvalidasi keberadaan keyword "dhruva", dan mencocokkan ID pengirim.

Fitur tambahan: Sistem "Linked Promo Accounts" (Akun Kerja). Pengguna dapat menautkan akun cadangan (clone/promo) mereka ke akun utama menggunakan OTP agar link promosi yang disebar menggunakan akun cadangan tetap dapat diklaim oleh akun utama.

## Perubahan yang Dilakukan
1. **Database Schema (`bot/database.py`)**
   - Menambahkan tabel `promo_verifications` untuk menyimpan antrean link.
   - Menambahkan tabel `linked_accounts` untuk menyimpan relasi Akun Utama dan Akun Kerja.
   - Menambahkan method pendukung: `add_linked_account`, `get_linked_accounts`, `add_promo_verification`, dll.

2. **Bot Handler (`bot/handlers/promo.py`)**
   - Membuat *handler* baru `/link_kerja` untuk *generate* kode OTP.
   - Membuat *handler* baru `/cek_akun_kerja` untuk melihat daftar akun yang ditautkan.
   - Membuat *handler* baru `/lpm <link>` untuk mensubmit link promosi ke database.
   - Membuat filter `MessageHandler` untuk mendeteksi pengiriman kode OTP dari Akun Kerja secara *private message*.

3. **Userbot Checker (`checker.py`)**
   - Membuat *script* baru berbasis Pyrogram yang melakukan *polling* ke database.
   - Memvalidasi usia link (maksimal 2x24 jam).
   - Memvalidasi isi pesan (keyword `dhruva`).
   - Memvalidasi pengirim pesan (sama dengan Akun Utama atau bagian dari `linked_accounts`).
   - Memberikan *reward* +1 Agra dan mengirim notifikasi jika lolos validasi.

4. **Dokumentasi**
   - Memperbarui `docs/database.md` dengan tabel baru.
   - Memperbarui `docs/commands.md` dengan daftar *command* baru.

## Pengujian
- Harus dipastikan kedua *script* berjalan beriringan (bisa melalui `systemctl`).
- Pengguna harus *login* Pyrogram terlebih dahulu di terminal untuk menghasilkan file sesi `checker.session`.
