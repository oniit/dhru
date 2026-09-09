# 071 - Menambahkan Argumen `all` Pada Command `/agra top`

## Latar Belakang
Secara bawaan, perintah `/agra top <role>` hanya akan menampilkan 17 pengguna dengan saldo Agra teratas. User meminta kemampuan untuk dapat melihat **seluruh** pengguna pada role tersebut beserta jumlah saldo Agranya tanpa terpotong limitasi Top 17.

## Solusi Teknis
1. Memodifikasi `cmd_agratop` pada `bot/handlers/commands.py` untuk mendeteksi apakah argumen `all` disematkan oleh pengguna.
2. Apabila `all` diberikan (contoh: `/agra top charya all`), maka bot tidak akan menyisipkan `LIMIT 17` ke dalam query Turso SQLite, sehingga dapat mengambil keseluruhan baris pengguna.
3. Karena output bisa sangat panjang jika data banyak (sehingga melebihi batas 4096 karakter di Telegram), output diumpankan ke fungsi asinkron pembantu `_reply_daftar_chunks`.
4. Fungsi `_reply_daftar_chunks` akan secara otomatis memecah output ke dalam beberapa blok/pesan dengan jeda waktu _sleep_ antardetik untuk mencegah pelanggaran Flood Control Telegram.

## Perubahan Kode
1. Mengedit `bot/handlers/commands.py` untuk menambahkan flag pengecekan kata `all`. Mengubah cara output dari `await update.message.reply_text()` biasa menjadi pemanggilan fungsi delegator `_reply_daftar_chunks`.
2. Menambahkan _hint_ di menu utama `cmd_agra_router` dan `docs/commands.md` agar user menyadari keberadaan fitur ini.
