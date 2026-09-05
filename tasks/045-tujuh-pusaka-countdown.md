# Tujuh Pusaka Round Countdown

## Apa yang Dikerjakan
Menambahkan fitur pengingat waktu (countdown) pada setiap ronde permainan "Tujuh Pusaka".

## Mengapa Dikerjakan
Atas permintaan pengguna, agar permainan Tujuh Pusaka memiliki pengingat waktu (seperti fitur yang sudah ada di game Kantong Rempah). Sebelumnya ronde dibatasi 2 menit tanpa ada pesan peringatan hingga tiba-tiba waktu habis. Dengan ini, pemain akan menerima notifikasi sisa waktu untuk mempercepat permainan.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. Menambahkan fungsi baru `job_tujuh_pusaka_round_reminder` di `bot/games/tujuh_pusaka.py`. Fungsi ini bertugas untuk mengecek apakah sesi game masih aktif, berada di fase bermain (`PHASE_PLAYING`), dan apakah masih di ronde yang sama dengan jadwal *job*-nya. Jika iya, maka pesan pengingat waktu akan dikirim.
2. Memodifikasi 3 tempat yang memicu dimulainya ronde (dan memicu *timeout job*):
   - `job_tujuh_pusaka_autostart` (saat game otomatis dimulai)
   - `paksa_mulai_tujuh_pusaka` (saat admin mengetik `/mulai_game`)
   - `resolve_round` (saat ronde berpindah ke ronde berikutnya)
3. Pada ketiga tempat tersebut, bot menjadwalkan tiga *job* baru dengan `run_once`:
   - Pada detik ke-60: Pesan sisa waktu 1 menit.
   - Pada detik ke-90: Pesan sisa waktu 30 detik.
   - Pada detik ke-105: Pesan sisa waktu 15 detik.
