# Task 041: Fix Story Validation

## Apa yang Dikerjakan
- Mengganti library `pyrogram` dengan `pyrofork` pada file `requirements.txt`.

## Mengapa Dikerjakan
- Pengguna melaporkan bahwa validasi bot untuk link Telegram Story selalu mengembalikan pesan "Terjadi kesalahan sistem saat mencoba membaca Story-mu", meskipun link Story tersebut benar dan masih tersedia.
- Setelah diinvestigasi, hal ini disebabkan oleh library Pyrogram resmi (versi `2.0.106`) yang digunakan sistem belum mendukung pengambilan Telegram Story (tidak ada metode `get_stories` pada class `Client`), sehingga akan memicu `AttributeError` dan lari ke blok pengecualian error sistem. 
- Library `pyrofork` (versi fork dari Pyrogram yang lebih up-to-date) sudah mengimplementasikan `get_stories` sehingga dapat membaca story Telegram dengan benar.

## Bagaimana Alur Kodenya Bekerja (Teknis)
- Dependensi di-update: `pip uninstall pyrogram` dan `pip install pyrofork` dijalankan.
- File `requirements.txt` diperbarui dari `pyrogram` menjadi `pyrofork`.
- Terdapat penyesuaian logika tambahan di dalam `checker.py` pada bagian parsing `story.media_areas`. Pyrofork mengembalikan objek `MediaAreaChannelPost` dengan atribut `chat` (tipe `Chat`), bukan sekadar `channel_id`. Oleh karena itu, kita memperbarui cara mengekstrak ID channel dengan `area_chat.id`.
- Script `checker.py` masih menggunakan import `from pyrogram import Client` karena `pyrofork` didesain sebagai drop-in replacement (menggunakan namespace module `pyrogram`).
- Ketika `checker.py` memanggil `app.get_stories()`, program akan memanggil metode milik `pyrofork` yang secara fungsional dapat berinteraksi dengan Telegram API untuk mengecek dan mem-parsing _media areas_ dari story, memungkinkan validasi repost (MediaAreaChannelPost) untuk berfungsi sebagaimana mestinya.
