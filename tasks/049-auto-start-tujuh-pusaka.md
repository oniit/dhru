# 049 - Auto Start Tujuh Pusaka

## Deskripsi
Menambahkan fitur *auto-start* (otomatis mulai) untuk game Tujuh Pusaka ketika berada di fase *lobby* pendaftaran. Sebelumnya, game ini akan berada di fase *lobby* selamanya jika tidak ada yang memicu perintah `/mulai_game`. Sekarang, game akan otomatis dimulai setelah 3 menit (180 detik) sejak pendaftaran dibuka.

## Perubahan Kode
- Memodifikasi fungsi `mulai_tujuh_pusaka` di `bot/games/tujuh_pusaka.py` untuk menjadwalkan 4 task `job_queue` baru:
  1. Pengingat 1 menit (pada detik ke-120)
  2. Pengingat 30 detik (pada detik ke-150)
  3. Pengingat 15 detik (pada detik ke-165)
  4. Auto-start (pada detik ke-180)
- Menambahkan fungsi baru `job_tujuh_pusaka_reminder` untuk menampilkan pengingat waktu di grup. Fungsi ini akan memastikan game masih di fase pendaftaran (`PHASE_REGISTRATION`) sebelum mengirim pesan, sehingga tidak spam jika game sudah terlanjur dimulai.
- Menambahkan fungsi baru `job_tujuh_pusaka_autostart` untuk secara otomatis memaksa game dimulai, yang mengeksekusi logika serupa seperti perintah `/mulai_game` (beralih ke `PHASE_PLAYING` dan menjalankan *timeout* ronde 1).

## Catatan
Jika tidak ada sama sekali pemain yang mendaftar (`len(state["players"]) == 0`) saat waktu 3 menit habis, game akan otomatis membatalkan sesinya dan menghapus sesi di database.
