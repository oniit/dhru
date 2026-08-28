# Fix /all Command untuk Pesan Caption dan Reply

## Deskripsi Masalah
User melaporkan bahwa perintah `/all pesan` tidak berfungsi. Setelah ditelusuri, masalah ini terjadi karena:
1. Saat user mengirim foto/media (caption) dengan tag `/all`, bot menggunakan `update.message.text` yang bernilai `None` untuk media, sehingga isi pesannya diabaikan dan pesan yang terkirim hanyalah teks bawaan "Tag semua".
2. Ketika `/all` di-reply pada suatu pesan, pesan balasannya tidak dikaitkan dengan *target reply* aslinya.
3. Saat admin memanggil perintah `/all`, admin (sebagai aktor) tidak dimasukkan ke daftar tag (agar tidak menge-tag diri sendiri), yang bisa menyebabkan bot mengembalikan "Belum ada user yang terdeteksi" jika ia sendirian/sedang *testing* karena daftar penerimanya jadi kosong.

## Solusi
1. Diperbarui logika untuk membaca input pesan dengan memakai:
   `raw_text = (update.message.text or update.message.caption or "").strip()`
   Sehingga caption foto/media tetap terbaca dan bisa di-broadcast melalui `custom_body`.
2. Menambahkan `reply_to_message_id=reply_to_id` dalam pemanggilan `update.message.reply_text`. Apabila user memakai `/all` dengan membalas pesan orang lain (atau bot), hasil tag akan diteruskan sebagai *reply* dari pesan tersebut, memberikan visibilitas yang jauh lebih baik untuk fitur "tagall".

## File yang Diubah
- `bot/handlers/commands.py` (pada fungsi `cmd_all`)

3. Menambahkan pengaman (try-except) saat bot mencoba membuat request ke userbot. Jika tabel userbot_requests tidak ditemukan di database (misal karena belum dimigrasi), bot tidak akan *crash* secara diam-diam, melainkan akan langsung memakai fallback group_seen_users.

4. Memperbaiki crash fatal akibat kurangnya import random pada fungsi internal pembuat list tag (mention batch). Sebelumnya, bot berhenti secara paksa (NameError) sesaat sebelum mengirim pesan Tag semua karena gagal memanggil random.choice.
