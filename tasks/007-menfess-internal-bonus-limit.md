# Task 007: Menfess Internal Role Enhancements

## Deskripsi
Implementasi penambahan fitur spesifik untuk pengguna dengan role `internal` pada sistem menfess.

## Perubahan yang Dilakukan
1. **Bonus Menfess Pertama (Cashback):** 
   - Modifikasi `execute_menfess` di `bot/handlers/menfess.py` untuk memberikan *cashback* sebesar 2 Agra kepada pengguna `internal` saat mereka mengirimkan menfess pertama pada hari tersebut.
   - Cashback sebesar 2 Agra diberikan dengan asumsi biaya pengiriman adalah 1 Agra, sehingga pengguna akan mendapatkan keuntungan bersih 1 Agra apabila mereka tidak memberikan gift tambahan, sesuai dengan permintaan agar ibaratnya "dapat bonus 1 agra kalau gak utak atik biaya agranya".
   - Penambahan fungsi pembantu `get_menfess_sent_today_count` di `bot/database.py` untuk menghitung jumlah menfess yang dikirim oleh pengguna pada hari yang sama. Kalkulasi start-of-day disesuaikan dengan zona waktu lokal (UTC+7).

2. **Pembatasan Penerima Berulang:**
   - Modifikasi `target_handler` di `bot/handlers/menfess.py` agar pengguna `internal` tidak dapat mengirim menfess kepada 7 penerima terakhir mereka yang berbeda **HANYA JIKA** itu adalah menfess pertama mereka hari ini (yang mendapatkan cashback). Jika mereka mengirim menfess kedua dan seterusnya (bayar normal), batasan ini tidak berlaku.
   - Penambahan fungsi pembantu `get_last_n_unique_menfess_receivers` di `bot/database.py` yang memanfaatkan klausa `GROUP BY receiver_id` dan `ORDER BY MAX(created_at) DESC` untuk mengambil `n` ID penerima unik terakhir dengan cepat.

3. **Peningkatan UX Input Hadiah:**
   - Setelah pengguna memasukkan nominal hadiah (gift), proses pengiriman tidak lagi dieksekusi secara otomatis.
   - Sistem kini akan memunculkan kembali menu konfirmasi pengiriman yang mencakup rekap biaya (1 Agra) + Hadiah + Total, beserta tombol `✅ Ya, Kirim`.
   - Tombol tambah hadiah berubah teksnya menjadi `🎁 Edit Nominal Hadiah ({jumlah} Agra)` agar pengguna tahu bahwa hadiah telah tersimpan dan dapat diubah sebelum dikirim.

## Alasan
Fitur ini ditambahkan untuk mendorong pengguna dengan role `internal` agar lebih aktif mengirim menfess setiap hari, dan di saat yang sama, memberikan variasi penerima pesan (tidak terfokus pada orang-orang yang sama secara berulang-ulang).

## Alur Kode
- Saat pengguna memasukkan target, `target_handler` memeriksa role pengirim. Jika `internal`, dilakukan pengecekan apakah hari ini ia sudah mengirim menfess. Jika belum (`sent_today == 0`), maka 7 penerima unik terakhir (dari `menfess_history`) diambil, lalu diperiksa apakah target baru ada di list tersebut. Jika iya, proses dihentikan. Jika sudah pernah mengirim menfess hari ini, pengecekan ini di-skip.
- Saat menfess dieksekusi (`execute_menfess`), dihitung apakah hari ini (berdasarkan timestamp UTC disesuaikan UTC+7) pengirim sudah mengirim menfess. Jika belum, dan role adalah `internal`, `cashback_amount` bernilai 2.
- Pemotongan biaya standar (-1 Agra - gift) tetap dijalankan di ledger, kemudian transaksi cashback (+2 Agra) dicatat secara terpisah di ledger dengan deskripsi "Bonus menfess pertama hari ini (Internal)".
- Pesan sukses yang dikirimkan ke pengirim turut menampilkan notifikasi mengenai cashback ini jika ia berhak mendapatkannya.
