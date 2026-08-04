# Pengaturan Pesan Media untuk Komunikasi Pengguna - Admin

## Ringkasan Fitur
Sistem komunikasi _Customer Service_ di mana pesan yang dikirim oleh pengguna ke bot secara otomatis diteruskan ke grup para admin (Petinggi Group) kini telah ditingkatkan kemampuannya untuk mendukung lalu lintas segala bentuk media (Foto, Dokumen, Video, Stiker, _Voice Note_, dll) dari kedua belah pihak.

## Alasan
Pada versi sebelumnya, sistem menggunakan filter `filters.TEXT` murni, sehingga jika pengguna mengirimkan _screenshot error_ (foto) atau dokumen, pesan tersebut akan diabaikan oleh bot. Sisi admin pun sebelumnya hanya bisa merespons balik ke pengguna menggunakan teks.

## Perubahan Teknis
### 1. Perubahan Router/Filter (di `bot/handlers/register.py`)
- Mengganti filter `filters.TEXT` menjadi pengecualian `~filters.COMMAND` agar segala bentuk *update* (media maupun teks) tertangkap.
- Mengubah referensi `messages.on_text` menjadi `messages.on_private_message`.
- Mengubah referensi `messages.on_group_text` menjadi `messages.on_group_message`.

### 2. Forwarding Pengguna -> Admin (di `bot/handlers/messages.py`)
- Mengganti penggunaan fungsi format *string* kaku dan `send_message`.
- Bot kini mengekstrak identitas pengirim dan membuatnya menjadi format *inline mention* yang aman dari _HTML Injection_ (menggunakan `html.escape()`).
- Jika pesan adalah **Teks Murni**: menggunakan `send_message` dengan menyematkan `#ID_...`.
- Jika pesan adalah **Stiker/Video Note** (tipe media yang secara teknis *API* Telegram tidak mendukung atribut *caption*): menggunakan `copy_message` untuk meneruskan media tersebut secara utuh, lalu bot secara terpisah mengirim pesan teks `#ID_...` sebagai balasan _(reply)_ dari media tersebut.
- Jika pesan adalah **Media Normal** (Foto, Dokumen, Video): menggunakan `copy_message` di mana tag identitas disisipkan tepat di bagian `caption` menggunakan `parse_mode="HTML"`.

### 3. Balasan Admin -> Pengguna
- Mengekstrak teks admin menggunakan _Regex_: `(?i)^#balas(?:\s+|$)(.*)`. Hal ini menjamin perlindungan terhadap karakter *Enter/Newline* maupun *Spasi*.
- Jika admin menekan *reply* pada media/teks pengguna dan membalas dengan teks murni: menggunakan `send_message`.
- Jika admin menekan *reply* dan merespons menggunakan Stiker/Video Note + *hashtag* `#balas`: Mengirim stiker dengan `copy_message` (karena *caption* tidak berlaku), tapi jika masih ada sisa teks balasan, teksnya dikirim terpisah.
- Jika admin merespons menggunakan **Foto/Dokumen + caption #balas <jawaban>**: bot akan menggunakan `copy_message` dan menimpa *caption* aslinya dengan *caption* `<jawaban>`.

Semua kasus *edge case* terkait ekstensi pengiriman media kini telah tercakup dengan aman.
