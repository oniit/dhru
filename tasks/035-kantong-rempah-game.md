# Task 035: Kantong Rempah Game

## Deskripsi
Game `kantong_rempah` dibuat berdasarkan logika game tebak-tebakan HTML sederhana yang diadaptasi menjadi game interaktif Telegram dengan arsitektur multi-fase (Setor -> Tebak -> Hasil) yang memanfaatkan bot `JobQueue` untuk kontrol batas waktunya.

## Perubahan Teknis
- **Game Engine**: `bot/games/kantong_rempah.py` berisi fungsionalitas inti: menginisiasi waktu (default 2 menit setor, 3 menit tebak), mengelola transisi setoran menggunakan `JobQueue`, menghitung acakan dari bot, serta kalkulasi selisih untuk pemenang.
- **Deep Linking (PC Interaksi)**: Menambahkan _handling_ URL `t.me/bot?start=rempah_<chat_id>` pada fungsi `cmd_start` di `bot/handlers/commands.py`. Fitur ini membuat bot mengubah status profil pengguna (lewat `onboarding_step = REMPAH_SETOR:<chat_id>`).
- **Private Message Interception**: Modifikasi fungsi `on_private_message` di `bot/handlers/messages.py` untuk mengizinkan bot membaca angka (0-10) yang di-input pengguna jika mereka dalam proses _onboarding_ `REMPAH_SETOR`. Angka tersebut kemudian dimasukkan ke database sesi game grup yang sesuai.
- **Tebakan di Grup**: `process_game_message` dalam `games.py` ditambahkan aturan membaca _command_ `/tebak <angka>` jika nama gamenya `kantong_rempah`, kemudian mengupdate _state_.

## Catatan
Sistem ini menggunakan penyimpanan `json` dinamis di _state_ tabel `game_sessions` untuk menampung angka, yang menjadikannya aman dan _scalable_ walau digunakan ratusan pemain karena operasinya berbasis manipulasi dictionary dan satu kali tulis ke tabel DB per _event_ interaksi.
