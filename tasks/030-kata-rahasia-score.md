# Peningkatan Sistem Skor Kata Rahasia

## Apa yang Dikerjakan
- Menambahkan fitur **Skor Sementara** pada command `/status` untuk game Kata Rahasia.
- Menambahkan command baru `/hasil` untuk menampilkan hasil akhir dari sesi game yang baru saja ditutup.
- Memberikan blok `try-except` (preventif) saat mengirim pesan hasil akhir pada saat `/berhenti` dijalankan agar sesi game tidak error.

## Mengapa Dikerjakan
- Pengguna ingin mengetahui skor sementara mereka ketika game sedang berjalan.
- Dibutuhkan langkah preventif atau *fallback* jika hasil akhir gagal dimunculkan secara otomatis karena masalah teknis (misal *rate limit* Telegram atau bot *restart* sesaat sebelum dikirim). 

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Skor Sementara**: Di `kata_rahasia.status_kata_rahasia`, kita mengekstrak objek `scores` dari JSON state game, mengurutkannya, lalu menampilkannya sebagai *leaderboard* Top 10 sementara.
2. **Preventif Error di `/berhenti`**: Pemanggilan `context.bot.send_message` dibungkus dengan `try-except` supaya jika *error*, status *database* yang menyatakan bahwa game telah dihentikan tetap tersimpan dengan aman (`is_active = 0`).
3. **Retrieval Historis dengan `/hasil`**: 
   - Membuat *method* baru `get_last_ended_game_session` di `bot/database.py` yang menargetkan sesi spesifik dengan `is_active = 0` dan *order by* `updated_at DESC`.
   - Command `/hasil <nama_game>` ditambahkan pada `bot/handlers/games.py` dan `register.py`.
   - Membuat fungsi `hasil_kata_rahasia` yang mengeksekusi format balasan pesan yang identik dengan pengumuman akhir game.
