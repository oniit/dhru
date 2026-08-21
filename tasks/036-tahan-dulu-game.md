# Task 036: Tahan Dulu Game

## Deskripsi
Fitur game baru bernama `tahan_dulu` (Adu Cepat/Reflex Game) diimplementasikan berdasarkan contoh kode Aiogram. Pemain harus menahan diri untuk tidak mengirim pesan apapun selama beberapa detik acak (atau statis dari parameter), lalu setelah waktu tersebut habis, pemain berlomba menjadi yang tercepat dalam merespons.

## Perubahan Teknis
- **Game Engine `bot/games/tahan_dulu.py`**:
  - `mulai_tahan_dulu`: Membaca argumen detik `delay_min`. Jika kosong, sistem menggunakan rentang acak 8-15 detik. Lalu membuat State ke `PHASE_WAITING`.
  - `proses_pesan_tahan_dulu`: *Listener* asinkron menggunakan `asyncio.Lock()` untuk mencegah bentrok pada *update* `state_json`. Semua pesan teks yang dikirim akan terekam waktu *delay*-nya (apakah lebih cepat dari waktu tunggu, atau berhasil menebak tepat pada waktunya).
  - `job_end_tahan_dulu`: *Job* yang mengeksekusi hasil ronde. Ia membagikan skor penalti (-2) dan bonus skor kecepatan respons (+5, +4, +3, +2, +1).
- **Sub-Menu Game**: Pada `bot/handlers/games.py`, fungsi `/bermain` sekarang mengecek argumen. Jika kosong, akan dikirimkan menu Markdown yang mencantumkan *list* semua game.
- **Intersepsi Pesan**: Di `process_game_message`, interceptor untuk `tahan_dulu` menggunakan properti pasif (`return False`) agar tidak menghambat *handler* lain seperti tracker aktivitas, tapi tetap membaca semua teks masuk.
