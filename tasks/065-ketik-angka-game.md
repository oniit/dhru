# 065: Menambah Game Ketik Angka

## Latar Belakang
User meminta tambahan mini-game baru bernama "Ketik Angka". Game ini bersifat adu cepat mengetik (fast typing).

## Logika & Aturan Main
1. Bot akan menentukan secara random antara 2 mode (Angka ke Huruf, atau Huruf ke Angka).
2. Angka diacak dari 100 hingga 9999999.
3. Contoh jika Angka ke Huruf, soal `342` harus dijawab `tiga empat dua`.
4. Contoh jika Huruf ke Angka, soal `satu enam` harus dijawab `16`.
5. 3 peserta pertama yang menjawab dengan benar akan mendapatkan skor (Juara 1 dapat 3 poin, Juara 2 dapat 2 poin, Juara 3 dapat 1 poin).
6. Game otomatis berhenti jika sudah mencapai 3 pemenang.

## Perubahan Kode
- **Baru:** `bot/games/ketik_angka.py` berisi logika game secara lengkap.
- **Modifikasi:** `bot/handlers/games.py` mendaftarkan `ketik_angka` di dictionary `AVAILABLE_GAMES`, mem-parsing argumen pada command `/bermain`, `/status`, `/berhenti`, `/hasil`, serta menangkap pesan grup secara natural melalui `process_game_message`.
- **Docs:** Mengupdate `docs/commands.md` dengan command baru `/bermain ketik_angka`.
