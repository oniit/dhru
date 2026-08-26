# Task 012: Integrasi Userbot untuk Fitur /tagall

**Deskripsi Singkat:**
Menambahkan kapabilitas kepada command `/tagall` dan `/all` agar dapat berkomunikasi dengan *userbot* (script `checker.py`) untuk mengambil seluruh anggota grup secara lengkap, dan bukannya sekadar mengandalkan memori (cache) bot. Jika userbot tidak ada atau tidak merespons, bot akan kembali menggunakan data *cache* grup (fallback).

**Alasan Pengerjaan:**
- Bot API (Telegram Bot) memiliki limitasi di mana ia tidak bisa secara natif mengambil daftar keseluruhan anggota *supergroup*. Ia hanya mengingat member yang pernah mengirim pesan.
- Karena *workspace* ini sudah memiliki *userbot* (menggunakan Pyrogram di `checker.py`), *userbot* bisa diperintahkan untuk melakukan tugas tersebut.

**Implementasi:**
1. **`bot/database.py`**:
   - Menambahkan tabel `userbot_requests` pada skema (SCHEMA). Tabel ini bertindak sebagai media IPC (Inter-Process Communication).
   - Menambahkan metode `create_userbot_request`, `get_userbot_request`, dan `update_userbot_request` untuk menyimpan dan membaca request.
2. **`checker.py`**:
   - Memodifikasi *main loop* agar selain mengecek request promosi, *userbot* juga memantau tabel `userbot_requests` yang berstatus `PENDING`.
   - Bila menemukan request `GET_MEMBERS`, ia akan memanggil fungsi iterasi asinkronus Pyrogram `app.get_chat_members()`. Hasil ID anggota dikumpulkan dalam array dan di-*dump* menjadi JSON ke dalam field `result`, lalu status diubah jadi `DONE`.
3. **`bot/handlers/commands.py`**:
   - Mengupdate fungsi `cmd_all` (dipanggil oleh `/tagall` dan `/all`). Kini fungsi tersebut akan melakukan insert *request* ke database dan memberi tahu user untuk menunggu: _"Sedang mengambil data anggota dari userbot..."_.
   - Bot melakukan *polling* (mengecek DB tiap 1 detik) maksimal 10 detik. 
   - Bila berhasil (`DONE`), daftar *mention* akan dibuat berdasarkan daftar komprehensif dari *userbot*. Bila gagal (limit 10 detik, error, dsb), ia otomatis beralih menggunakan data tabel `group_seen_users`.
4. **`docs/database.md`**:
   - Dokumentasi telah diubah untuk mencantumkan rincian tabel baru ke-13, yaitu `userbot_requests`.
