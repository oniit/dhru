# Task 019: Fix HTML parsing error in Menfess & adjust link previews
    
## Latar Belakang
Ditemukan dua *bug* tambahan:
1. Pesan *forward* ke grup petinggi memunculkan *preview profile* yang memakan banyak tempat ketika format link diubah ke `https://t.me/username`. Klien meminta agar bisa kembali diklik seperti username biasa tanpa *preview* kotak.
2. Salah satu pengirim gagal mengirim menfess ke *channel* (muncul notifikasi pengembalian saldo), padahal akun lain berhasil mengirim.

## Akar Masalah
1. **Link Preview:** Link berawalan `http(s)://` secara bawaan (*default*) akan merangsang Telegram memunculkan *web page preview*. 
2. **Menfess Gagal Kirim:** Masalah terjadi karena teks yang diketik pengirim kemungkinan mengandung karakter spesial HTML seperti `<`, `>`, atau `&`. Saat bot mencoba mengirimkan menfess ke *channel* menggunakan pengaturan `parse_mode="HTML"`, API Telegram gagal memprosesnya (*Bad Request: can't parse entities*) karena menganggap karakter tersebut sebagai *tag* HTML yang tidak tertutup sempurna. Sistem merespon kegagalan *channel* ini dengan membatalkan (*rollback*) seluruh transaksi dan mengembalikan saldo.

## Perubahan yang Dilakukan
- **bot/handlers/messages.py:**
  - Mengembalikan format link profil menggunakan `https://t.me/username` agar klik secara *native* langsung masuk ke profil pengguna.
  - Menambahkan argumen `disable_web_page_preview=True` pada `send_message` untuk mencegah munculnya kotak *preview* jelek di grup petinggi.
- **bot/handlers/menfess.py:**
  - Menambahkan pemrosesan `html.escape()` pada nama target (`target_name`) dan isi pesan (`message_text`). Perubahan ini akan menetralisir semua simbol seperti `<` menjadi `&lt;` sebelum dikirim ke channel dan *private chat*, sehingga API Telegram tidak lagi mengalami *error* gagal *parsing*.
  - Menambahkan proteksi `html.escape()` pada perintah pembacaan (`/menfess_read`).
