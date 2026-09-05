# 060 - Modifikasi Game Tahan Dulu (Kata Spesifik)

## Apa yang Dikerjakan
Menambahkan kemampuan pada game `Tahan Dulu` agar bot dapat memfilter pesan berdasarkan kata tertentu (*valid words*).

## Mengapa Dikerjakan
Sebelumnya, game Tahan Dulu akan merespons obrolan/pesan apapun saat ronde aktif, yang mungkin menyebabkan obrolan biasa (yang tidak bermaksud bermain) ikut kena penalti kepagian. Dengan adanya *valid words*, admin dapat membatasi pesan apa yang sah dihitung.

## Bagaimana Secara Teknis
1. Mengubah rute fungsi `cmd_atur` di `bot/handlers/games.py` untuk mendukung `tahan_dulu` (`elif game_name == "tahan_dulu": await tahan_dulu.atur_tahan_dulu(...)`).
2. Membuat fungsi baru `atur_tahan_dulu` di `bot/games/tahan_dulu.py` untuk memproses *input* string koma menjadi array, lalu menyimpannya menggunakan `db.upsert_game_setting()`.
3. Memodifikasi argumen pemanggilan `/bermain tahan_dulu` (`mulai_tahan_dulu`). Format sekarang dapat menerima dua argumen: `[setting_name]` (string) dan `[delay]` (integer). Jika `setting_name` diberikan, ia akan di-*fetch* dari *database*.
4. Memodifikasi deteksi pesan di `proses_pesan_tahan_dulu`. Jika di dalam `state_json` terdapat array `valid_words`, maka bot hanya akan memproses `msg_text.strip().lower()` yang cocok eksak (exact match) dengan elemen `valid_words`. Pesan lain diabaikan `return`.
