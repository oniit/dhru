# Bugfix: Maba Early Small Group Link 

## Apa yang Dikerjakan
Memperbaiki celah logika (*logical loophole*) pada alur `/lengkapi` khusus untuk pengguna berstatus Maba yang belum memasukkan Gencode.

## Mengapa Dikerjakan
Sebelumnya, jika pengguna dengan role `maba` menyelesaikan pengisian datanya (melalui `/lengkapi`) sebelum mereka menebus Gencode (Kode Akses) yang diberikan di Grup OSPEK, bot akan secara default menganggap mereka masuk ke "Kelompok 1" dan langsung memberikan link *invite* ke grup Kelompok 1 secara prematur. Hal ini berpotensi membuat satu Maba memiliki dua link grup kelompok yang berbeda (Kelompok 1, lalu kelompok asli mereka saat Gencode ditebus nanti).

Tindakan ini tidak membatasi kebebasan Maba untuk mengeksplor bot (menggunakan *command* lain seperti `/help` atau `/lengkapi`), melainkan hanya menunda pemberian link spesifik kelompok hingga Maba tersebut benar-benar sudah memiliki data `maba_group` hasil dari *redeem* Gencode.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Modifikasi `bot/handlers/commands.py` (Command `/lengkapi`)**:
   - Di dalam tahapan *finish* `/lengkapi` saat mengecek `elif role == "maba":`, ditambahkan validasi kondisi keberadaan properti `maba_group` pada `profile`.
   - `if "maba_group" not in profile:` -> Jika properti ini belum ada (artinya Maba belum *redeem* Gencode), bot tetap akan mengeset status data sudah lengkap (`LENGKAPI_DONE_KEY: True`), namun **tidak** men-generate link grup. Bot sebaliknya akan memberikan pesan peringatan agar pengguna menunggu instruksi dan menukarkan Gencode di Grup OSPEK General.
   - `else:` -> Jika properti sudah ada (artinya pengguna hanya melengkapi sisa datanya paska *redeem* Gencode), bot akan menarik nilai `mg = int(profile.get("maba_group", 1))` dan membuatkan *one-time invite link* untuk grup kelompok tersebut (seperti perilaku normalnya).
