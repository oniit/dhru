# Task 042: Mewajibkan 1x Promosi Sebelum Grup OSPEK

## Apa yang Dikerjakan
- Menambahkan syarat "Wajib 1x Promo" (baik via `/lpm` ataupun `/story`) di antara proses pendaftaran "Alasan Bergabung/Verifikasi Channel" dan langkah pemberian link grup OSPEK.
- Menambahkan tombol _inline_ `[ 🎁 Ambil Link OSPEK ]` dengan *callback query* `maba:claim_ospek`.
- Menambahkan fungsi pembantu database `count_valid_promos` untuk mengecek apakah user sudah memiliki minimal 1 promosi berstatus 'VALID'.

## Mengapa Dikerjakan
- Untuk memastikan setiap MABA secara nyata telah mempromosikan OPSTUD (via lpm/story) sebelum mereka benar-benar di-acc (diberi peran maba) dan dimasukkan ke grup OSPEK. Ini menghindari kecurangan pendaftar yang mungkin bolong tidak mengerjakan promosi.

## Bagaimana Alur Kodenya Bekerja (Teknis)
- Modifikasi dilakukan pada `bot/handlers/messages.py` dan `bot/handlers/commands.py`.
- Sebelumnya, pendaftar akan langsung diberikan status `ROLE_MABA` dan link grup OSPEK sesaat setelah mengisi Alasan atau memverifikasi Channel Wajib.
- Sekarang, pemberian role dan link ditahan. Pengguna justru diberikan pesan status `MABA_PROMO_WAIT` dan diinstruksikan untuk menyetor 1x promosi.
- Saat mereka menekan tombol `Ambil Link OSPEK`, sistem akan mencari jumlah riwayat promosi mereka di tabel `promo_verifications` dengan status `'VALID'` (ini ditangani oleh bot latar belakang / _checker.py_ secara independen).
- Jika riwayat promo valid ≥ 1, barulah pendaftaran dirampungkan (role di-set menjadi `maba`, dikirimi link grup, dan data profil diteruskan ke `PENDAFTAR_CH_ID`).
- Jika 0, maka bot akan memunculkan peringatan (Pop-up alert) agar mereka menanti atau melakukan promosi terlebih dahulu.
- Solusi ini sangat elegan karena sama sekali tidak perlu mengganggu/merekacipta ulang _script_ latar belakang (`checker.py`) yang selama ini sudah berjalan sangat baik.
