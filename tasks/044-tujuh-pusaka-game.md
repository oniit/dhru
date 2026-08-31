# 044 - Tujuh Pusaka Game

## Apa yang Dikerjakan
Menambahkan modul mini-game baru bernama "Tujuh Pusaka".
Ini adalah permainan *card battle* di mana sekumpulan pemain di dalam grup akan melawan Bot menggunakan 7 kartu khusus.
Kartu-kartu tersebut memiliki atribut *Strength* (Str) dan *Power* (efek spesial) masing-masing.

## Mengapa Dikerjakan
Permintaan dari user untuk membuat mekanisme game pertempuran kartu antara Camaba/Kelompok melawan bot sebagai bagian dari kegiatan "Tujuh Pusaka".

## Alur Kode Secara Teknis
1. **State Management**:
   Permainan memanfaatkan tabel `game_sessions` di SQLite yang sudah ada. *State* permainan disimpan dalam bentuk JSON yang berisi `phase` (`registration`, `playing`, `finished`), `round` (1-7), data `players` (menyimpan kartu tersisa, skor, penalti), dan `bot_cards` (kartu bot yang tersisa).

2. **Fase Registrasi**:
   Game dimulai dengan command `/bermain tujuh_pusaka`. Pemain di grup dapat mendaftar dengan command `/ikut`. Setelah pemain siap, inisiator game (atau admin) dapat menggunakan command `/mulai_game` untuk beralih ke fase bermain (Ronde 1).

3. **Fase Bermain**:
   Game berlangsung selama 7 ronde.
   - Pada setiap ronde, pemain mengetikkan `/pusaka <nama_kartu>` di grup.
   - Bot memberikan batas waktu maksimal 2 menit. Jika semua pemain terdaftar sudah memilih sebelum waktu habis, ronde otomatis diselesaikan.
   - Bot juga memilih 1 kartu secara acak dari sisa kartunya.

4. **Kalkulasi Duel**:
   - Duel dihitung secara individu: Kartu Pemain vs Kartu Bot.
   - Bot mengeksekusi Power dari masing-masing kartu, seperti membatalkan bonus, menambahkan Str terhadap tipe tertentu, membalikkan hasil duel (Kartu Pusaka), atau memberikan penalti -20 di ronde berikutnya (Neil).
   - Pemain yang memenangkan duel mendapatkan 1 Poin Menang (Win).

5. **Fase Selesai**:
   Setelah ronde 7 berakhir, bot menampilkan papan skor akhir yang diurutkan berdasarkan jumlah kemenangan terbanyak.
