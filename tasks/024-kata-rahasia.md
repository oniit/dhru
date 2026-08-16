# Kata Rahasia Game

## Apa yang Dikerjakan
Mengimplementasikan modul game baru bernama **Kata Rahasia** untuk dimainkan di dalam grup Telegram. Menggunakan arsitektur *Game Router* yang modular sehingga mendukung penambahan game lain secara general.

## Mengapa Dikerjakan
Untuk memberikan fitur interaktif bagi komunitas/grup (MVP: tebak kata rahasia yang tersembunyi). Arsitektur umum dibutuhkan agar command seperti `/atur` dan `/bermain` dapat dipakai ulang jika ke depannya ada game seperti Mafia atau Werewolf.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Database Modifikasi (`bot/database.py`)**: 
   - Tabel `game_settings`: Menyimpan konfigurasi game. Admin mengatur dengan `/atur kata_rahasia <setting> <kata1>, <kata2>...` dan JSON kata tersimpan.
   - Tabel `game_sessions`: Menyimpan sesi aktif di sebuah `chat_id`. Kolom `state_json` menyimpan daftar kata aktif dan skor pemain.
2. **Game Router (`bot/handlers/games.py`)**:
   - Mendaftarkan command `/atur`, `/bermain`, `/status`, dan `/berhenti`.
   - Router akan memecah *argument* pertama sebagai `game_name` dan mem-forward eksekusinya ke modul spesifik (contoh: `bot.games.kata_rahasia`).
3. **Kata Rahasia Logic (`bot/games/kata_rahasia.py`)**:
   - `atur_kata_rahasia`: Mem-parsing input kata (pisahkan koma) dan menyimpannya.
   - `mulai_kata_rahasia`: Menginisialisasi *session* dengan *state* `scores` kosong dan kumpulan kata dari *setting*.
   - `proses_pesan_kata_rahasia`: Dipanggil setiap ada pesan grup jika ada game yang aktif. Menggunakan reguler ekspresi (`re.search(r"\b...\b")`) untuk menemukan kecocokan yang eksak, menambah skor, dan menonaktifkan/hangus kata tersebut. Game berhenti otomatis saat kata habis.
4. **Hook Core Bot (`bot/handlers/messages.py`)**:
   - Pada fungsi `on_group_message`, sebelum pesan diteruskan ke admin/petinggi, pesan dilempar ke `process_game_message` milik Router untuk dicek apakah mencetak skor.
