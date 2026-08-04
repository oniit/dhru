# Task 005: Penutupan Bug pada Fitur Forward Pesan & Refaktor Nama Variabel

## Deskripsi Pekerjaan
1. Menutup celah bug (`Chat not found`) yang terjadi saat pengguna mengirimkan teks (termasuk input *username* saat menfess). Sebelumnya, setiap input teks diproses oleh bot dan diteruskan (di-*forward*) ke `FORWARD_GID`. Jika ID `FORWARD_GID` salah atau bot tidak ada di grup tersebut, maka proses tersebut menyebabkan aplikasi crash.
2. Mengganti nama variabel `FORWARD_GID` menjadi `PETINGGI_GID` agar fungsinya lebih jelas, yaitu sebagai grup internal untuk petinggi (bukan untuk keperluan menfess).

## Alasan (Why)
- Untuk mencegah crash di masa mendatang ketika grup untuk *forward* pesan tidak valid. Fitur utama (seperti *menfess* yang menggunakan *ConversationHandler*) terganggu akibat gagalnya proses *forward* pesan yang menangkap semua input teks.
- Mengubah penamaan variabel lingkungan (_environment variable_) menyesuaikan dengan konteks fungsionalnya (grup untuk *petinggi*), sesuai permintaan *user*.

## Alur Implementasi
1. **`messages.py`**:
   - Menambahkan blok `try-except` di sekitar fungsi `await context.bot.send_message(chat_id=FORWARD_GID, ...)` di dalam *handler* `on_text`.
   - Mengganti semua referensi `FORWARD_GID` menjadi `PETINGGI_GID`.
2. **`settings.py`**:
   - Mengubah inisialisasi lingkungan variabel dari `FORWARD_GID` menjadi `PETINGGI_GID`.
3. **`.env`**:
   - Menyesuaikan _key_ konfigurasi dari `FORWARD_GID` menjadi `PETINGGI_GID`.
