# 028 - Teruskan Data Pendaftaran Maba ke Channel

## Apa yang Dikerjakan
1. Menambahkan pemuatan _environment variable_ `PENDAFTAR_CH_ID` pada `bot/settings.py`.
2. Menambahkan logika pengiriman pesan ke channel `PENDAFTAR_CH_ID` pada `bot/handlers/messages.py` dan `bot/handlers/commands.py` saat proses registrasi MABA selesai (bersamaan dengan saat bot memberikan tautan/grup OSPEK).

## Mengapa Dikerjakan
Fitur ini mempermudah admin/panitia untuk memantau pendaftaran MABA secara _real-time_. Ketika mahasiswa baru menyelesaikan langkah memasukkan nama dan alasan, datanya otomatis diteruskan ke channel agar bisa dicatat/direkapitulasi tanpa harus mengecek database secara manual.

## Bagaimana Alur Kodenya Bekerja
1. Variabel `PENDAFTAR_CH_ID` dibaca dari `.env` dan di-_expose_ melalui `bot/settings.py`.
2. Saat tahap akhir pendaftaran MABA (_onboarding step_ selesai dan bot mengeluarkan link OSPEK), kode akan mengambil `full_name` dan `join_reason` dari profil pendaftar. 
3. Hal ini ditangani dalam 2 kemungkinan alur (baik melalui `MABA_REASON` secara langsung jika `MABA_CH_IDS` kosong, maupun setelah validasi subscription via callback query `maba:verify`).
4. Bot menyertakan _username_ pengguna dan membuat nama lengkapnya menjadi tautan profil (menggunakan format `[Nama](tg://user?id=UID)`).
5. Bot memanggil `context.bot.send_message` untuk mengirimkan pesan berformat Markdown ke `PENDAFTAR_CH_ID`. Jika gagal, _exception_ akan ditangkap dan dicatat oleh `logger`.
