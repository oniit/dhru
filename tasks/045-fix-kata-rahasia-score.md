# 045 - Fix Kata Rahasia Score Bug

## Apa yang Dikerjakan
Memperbaiki bug pada mini-game "Kata Rahasia" di mana poin dari tebakan kata terakhir tidak masuk ke dalam kalkulasi hasil akhir game.

## Mengapa Dikerjakan
Berdasarkan keluhan (laporan *screenshot*), saat seorang pengguna menebak kata terakhir yang mengakhiri game `kata_rahasia`, pengguna tersebut mendapatkan notifikasi penambahan poin, namun poin tersebut tidak terefleksi pada pesan "HASIL AKHIR". Hal ini terjadi karena _state_ permainan (seperti skor terbaru) yang telah disimpan ke dalam *database* belum disinkronisasi ke dalam *dictionary* `session` di *memory* sebelum fungsi `berhenti_kata_rahasia` dipanggil. Akibatnya, `berhenti_kata_rahasia` menggunakan data JSON lama yang belum memperbarui skor untuk tebakan terakhir.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. Di dalam `bot/games/kata_rahasia.py` pada fungsi `proses_pesan_kata_rahasia`, setelah memperbarui _database_ menggunakan `await db.update_game_session_state(conn, session["id"], state)`, ditambahkan kode baru: `session["state_json"] = json.dumps(state)`.
2. Perubahan ini memastikan objek `session` yang diteruskan dari `proses_pesan_kata_rahasia` ke `berhenti_kata_rahasia` memiliki string `state_json` paling mutakhir.
3. Saat `berhenti_kata_rahasia` me-load `json.loads(session["state_json"])`, nilai _scores_ yang didapatkan sekarang sudah termasuk tambahan poin dari tebakan yang baru saja mengakhiri sesi, sehingga papan peringkat hasil akhir menjadi akurat dan sinkron.
