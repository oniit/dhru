# 031 - Pengumuman Alokasi Kelompok MABA ke Grup

## Apa yang Dikerjakan
1. Mengembalikan pemuatan _environment variable_ `KELOMPOK_GID` di `bot/settings.py`.
2. Menambahkan logika pada _handler_ `INPUT_CODE` di `bot/handlers/messages.py` untuk secara otomatis mengirimkan notifikasi ke `KELOMPOK_GID` setiap kali seorang MABA berhasil menukarkan kode akses dan dialokasikan ke sebuah kelompok.

## Mengapa Dikerjakan
Fitur ini dibutuhkan agar admin atau panitia di grup `KELOMPOK_GID` dapat langsung mengetahui (mendapat notifikasi) ketika seorang MABA selesai menggunakan kodenya dan ditempatkan di kelompok tertentu (Kelompok 1-4). 

## Bagaimana Alur Kodenya Bekerja
1. Variabel `KELOMPOK_GID` dibaca dari `.env` dan di-_expose_ melalui `bot/settings.py`.
2. Saat seorang MABA memasukkan kode (pada _step_ `INPUT_CODE`) dan perannya tervalidasi sebagai `"maba"`, sistem menghitung urutan (`m_order`) dan menentukan kelompoknya (`maba_group`).
3. Setelah data kelompok disimpan, bot mengekstrak nama dan _username_ MABA tersebut dari *database*.
4. Bot menyusun pesan berisi nama, _username_, kelompok, serta kode yang digunakan, lalu memanggil `context.bot.send_message` untuk mengirimkannya ke `KELOMPOK_GID`.
5. Jika pengiriman gagal (misalnya karena bot tidak berada di dalam grup tersebut), sistem akan mencatatnya di *log* sehingga tidak mengganggu alur MABA untuk mendapatkan *link invite*.
