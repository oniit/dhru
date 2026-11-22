# Task 160: Perbaikan False-Failure & Timeout IPC pada Perintah /pfp serta Reward Agra

## Latar Belakang & Masalah
Pengguna melaporkan kendala pada perintah `/pfp`:
> "/pfp kok tulisannya gagal forward tp saya cek chnya keforward kok, jadinya gak dpt agra deh"

Ketika pengguna memanggil perintah `/pfp` dengan tautan channel Telegram (terutama dari channel privat atau channel di mana bot tidak memiliki izin forward langsung), bot Telegram melaporkan:
`❌ Gagal mem-forward post.`
dan saldo Agra pengguna tidak bertambah (+0 Agra). Namun ketika channel tujuan (`KEEP_CH_ID`) diperiksa, postingan tersebut sebenarnya **berhasil ter-forward**!

## Analisis Akar Masalah (Root Cause)
Setelah dilakukan pelacakan menyeluruh (*holistic debugging*), ditemukan tiga faktor utama:
1. **Timeout Polling IPC Terlalu Singkat (Premature Timeout)**:
   - Pada `bot/handlers/pfp.py`, fungsi fallback userbot `_forward_via_userbot_ipc` hanya melakukan polling selama 12 iterasi dengan jeda 0.5 detik (`12 * 0.5 = 6.0 detik`).
   - Sementara itu, worker `checker.py` memiliki siklus tidur *idle* sebesar **3.5 detik** (`await asyncio.sleep(3.5)`) untuk melindungi kuota baca Turso sesuai aturan `AGENTS.md`.
   - Ketika request IPC dimasukkan ke tabel `userbot_requests`, jika `checker.py` sedang berada dalam fase tidur atau sedang menjalankan verifikasi promo lain, `checker.py` membutuhkan 2-4 detik untuk bangun, ditambah waktu eksekusi MTProto Pyrogram (`messages.ForwardMessages`) yang memakan waktu 2-4 detik lewat jaringan Telegram.
   - Total waktu eksekusi riil umumnya berkisar antara **6.5 hingga 8.5 detik**.
   - Karena `_forward_via_userbot_ipc` menyerah di detik ke-6.0, fungsi mengembalikan nilai `0` (*timeout*), bot menampilkan pesan kegagalan, dan reward Agra tidak dieksekusi.
   - Sekitar 0.5–1 detik kemudian, `checker.py` berhasil menyelesaikan pengiriman postingan ke Telegram KEEP channel, sehingga postingan muncul di channel tujuan tetapi bot sudah telanjur menyatakan gagal.

2. **Urutan Pemrosesan Antrean di `checker.py`**:
   - `checker.py` sebelumnya memproses `userbot_requests` di bagian paling akhir setelah memproses semua link `promo_verifications`. Jika ada antrean promo yang sedang diproses, eksekusi IPC tertunda lebih lama.

3. **Penghitungan Objek Return Pyrogram**:
   - Di `checker.py`, pemanggilan `app.forward_messages` menghasilkan objek `Message` atau list `Message`. Penggunaan `len(res) if res else len(chunk)` berisiko memicu `TypeError` jika `res` berupa objek tunggal tanpa `__len__`, yang memicu *fallback* individual ganda yang memakan waktu tambahan.

## Solusi & Perubahan Teknis
1. **Peningkatan Batas Waktu & Optimalisasi Polling `_forward_via_userbot_ipc` (`bot/handlers/pfp.py`)**:
   - Menaikkan durasi batas tunggu dari 6.0 detik menjadi **25.0 detik**.
   - Mengubah jeda polling menjadi 1.0 detik berbasis `time.monotonic()` untuk meminimalkan beban *rows read* Turso (maksimal 25 pembacaan, dan langsung *break/return* segera setelah status berubah menjadi `DONE`).
   - Menjamin bahwa jika status `DONE` tercapai, nilai postingan ter-forward diambil secara akurat dan fungsi mengembalikan jumlah forward yang berhasil, sehingga `db.log_pfp_forward` dan `db.add_agra` tereksekusi dengan benar.

2. **Prioritas Pemrosesan IPC di `checker.py`**:
   - Memanggil `process_userbot_requests(conn)` di **awal** setiap siklus `while True` dalam `process_pending_links()` agar perintah interaktif langsung pengguna (seperti `/pfp`) segera diproses tanpa harus menunggu siklus verifikasi promo selesai.
   - Tetap memproses ulang di akhir siklus jika ada antrean baru yang masuk selama verifikasi promo berjalan.

3. **Penanganan Objek Pesan yang Aman (`checker.py`)**:
   - Memperbaiki perhitungan `fwd_count`:
     ```python
     if isinstance(res, list):
         fwd_count += len(res)
     elif res is not None:
         fwd_count += 1
     ```

4. **Penambahan Suite Pengujian & QA Master Audit**:
   - Menambahkan pengujian di `tests/test_pfp_deep.py` untuk respons tunda IPC (`test_deep_ipc_delayed_response_within_timeout`), penanganan timeout maksimal (`test_deep_ipc_timeout_returns_zero`), dan verifikasi penghitungan objek return forward (`test_deep_checker_forward_counting_logic`).
   - Semua 46 pengujian unit pfp & warkat lulus 100%.
   - Semua 93 pengujian pada Master QA Audit (`tests/test_qa_master_audit.py`) lulus 100%.

## Panduan untuk Pengguna
- Untuk postingan yang sebelumnya sudah masuk ke channel namun belum mendapatkan Agra karena bot telanjur melaporkan gagal, Owner dapat menambahkan +1 Agra secara manual menggunakan perintah:
  `/addagra @username 1`
- Untuk penggunaan perintah `/pfp` selanjutnya, bot kini memiliki toleransi tunggu hingga 25 detik dan worker `checker.py` merespons secara instan di awal siklus, sehingga status berhasil (`✅ 1 post berhasil diforward... (+1 Agra)`) akan selalu sinkron dengan postingan yang masuk ke channel penyimpanan.
