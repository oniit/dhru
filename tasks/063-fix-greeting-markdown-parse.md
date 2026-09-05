# Fix BadRequest: Can't parse entities pada Preview Greeting

## Latar Belakang
User melampirkan log *error* dari VPS (production) yang menunjukkan `telegram.error.BadRequest: Can't parse entities: can't find end of the entity starting at byte offset 338`. Error ini umumnya terjadi saat ada karakter khusus Markdown yang tidak memiliki penutup (unbalanced/unescaped).

## Akar Masalah
Pada file `bot/handlers/commands.py` untuk perintah `/greeting`, sistem mencoba mencetak preview pesan selamat datang (greeting) milik suatu grup. Namun, `cmd_greeting` secara _hardcode_ menggunakan pengaturan `parse_mode="Markdown"`.

Jika admin grup sebelumnya memasukkan teks custom yang mengandung karakter khusus (seperti `_`, `*`, `[`) tetapi tidak menutupnya, atau murni ingin menggunakan tag HTML biasa, parser Telegram akan menolaknya dengan error `BadRequest`. Hal ini kontras dengan implementasi asli saat bot menyambut *member* baru di `bot/handlers/messages.py`, di mana bot menggunakan `parse_mode="HTML"`. Ketidakselarasan ini menyebabkan perintah preview (`/greeting`) gagal menampilkan pesan dan justru memicu _exception_.

## Perubahan yang Dilakukan
- Memodifikasi `cmd_greeting` pada `bot/handlers/commands.py` dengan mengganti `parse_mode="Markdown"` menjadi `parse_mode="HTML"`.
- Mengubah format instruksi cetak miring tambahan dari sintaks Markdown `*(Untuk mengubah ketik /setgreeting)*` menjadi sintaks HTML `<i>(Untuk mengubah ketik /setgreeting)</i>`.
- Melakukan *escape* pada karakter kurung sudut khusus pada pesan jika tidak ada greeting yang diatur, menjadi `&lt;pesan&gt;` agar kompatibel dengan tag HTML.
