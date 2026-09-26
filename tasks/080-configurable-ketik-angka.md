# Configurable Ketik Angka Winners

## Deskripsi
Memodifikasi mini-game `ketik_angka` sehingga jumlah pemenang yang dicari bisa diatur secara spesifik saat permainan dimulai. Default pemenang juga diubah dari 3 menjadi 1 orang saja.

## Perubahan Kode
- **`bot/games/ketik_angka.py`**:
  - Menambahkan argumen `args_text` pada fungsi `mulai_ketik_angka`.
  - Melakukan parsing pada argumen untuk membaca integer (jumlah maksimal pemenang yang dicari, maksimal 10). Jika tidak disebutkan, default-nya adalah 1.
  - Memasukkan `max_winners` ke dalam state game.
  - Menyesuaikan kalkulasi skor pada `proses_pesan_ketik_angka` (Pemenang pertama mendapat 3 poin jika max_winners=1, sebaliknya proporsional).
  - Menyesuaikan batas akhir dan pesan status (`status_ketik_angka`).
- **`bot/handlers/games.py`**:
  - Menyesuaikan `cmd_bermain` untuk *parsing* argumen setelah perintah `/bermain ketik_angka` dan meneruskannya ke fungsi `mulai_ketik_angka` menggunakan variabel `args_text`.
- **`docs/commands.md`**:
  - Memperbarui dokumentasi terkait perintah `/bermain ketik_angka [max_pemenang]`.
