# 128: Implementasi Game Baru "Caksoria"

## Latar Belakang & Kebutuhan
Pengguna meminta penambahan mini-game baru bernama **"caksoria"** yang berbasis mekanisme permainan refleks dan tahan waktu mirip dengan `tahan_dulu`, namun dengan aturan khusus:
1. Nama game: `caksoria`.
2. Pencatatan partisipan: Semua pesan dicatat (tidak hanya pesan yang sesuai keyword).
3. Batas waktu penerimaan respons: 30 detik setelah waktu tahan selesai (berbeda dari `tahan_dulu` yang 11 detik).
4. Format output hasil: `"emoji + nama + detik"` tanpa skor/poin kumulatif.
   - 🥳 untuk yang sesuai keyword dan tidak kecepetan ($\ge$ delay detik).
   - 👺 untuk yang kecepetan ($<$ delay detik) atau tidak sesuai format keyword.

## Implementasi Teknis

### 1. Modul Game Baru: `bot/games/caksoria.py`
- **Inisiasi & Konfigurasi**:
  - `mulai_caksoria(update, context, db, conn, args_text)`:
    - Menerima argumen format `/bermain caksoria [setting_name] [delay_seconds]` atau `/bermain caksoria [delay_seconds]`.
    - Jika delay tidak ditentukan, default acak antara 7 hingga 17 detik.
    - Menjadwalkan pengakhiran ronde otomatis via job queue: `delay_min + 30` detik dengan nama job `caksoria_{chat_id}`.
- **Pencatatan Pesan**:
  - `proses_pesan_caksoria(update, context, db, conn, session)`:
    - Menggunakan asynchronous lock (`game_locks[session_id]`) untuk konsistensi data.
    - Mencatat seluruh pesan pertama dari setiap pengguna (`user_ids` guard: 1 user hanya dinilai 1x).
    - Menghitung delta waktu `diff = now - start_time`.
    - Memeriksa kesesuaian kata kunci valid (`valid_words`).
    - Menentukan emoji:
      - `diff < delay_min`: `👺` (kecepetan)
      - `not matches_keyword`: `👺` (tidak sesuai format)
      - `diff >= delay_min and matches_keyword`: `🥳` (sesuai keyword)
    - Menyimpan profil entri: `uid`, `name`, `diff`, `text`, `matches_keyword`, `emoji`.
- **Pengumuman Hasil**:
  - `job_end_caksoria(context)` & `hasil_caksoria(...)`:
    - Mengurutkan entri berdasarkan waktu respon `diff` terkecil (tercepat).
    - Memformat setiap baris persis sesuai spesifikasi:
      ```
      👺 zoldy: 5.43s
      🥳 dika: 8.18s
      👺 cecil: 8.25s
      👺 bena: 9.12s
      🥳 abel: 32.09s
      ```
    - Menyertakan legenda emoji sebagai keterangan.
    - Mengakhiri sesi di basis data remote Turso secara bersih (`end_game_session`).
- **Pengaturan & Kontrol**:
  - `atur_caksoria`: Mengonfigurasi kata kunci valid melalui `/atur caksoria <setting_name> <kata1>, <kata2>, ...`.
  - `status_caksoria`: Memeriksa waktu berjalan, sisa waktu, dan jumlah respon terdata.
  - `berhenti_caksoria`: Membatalkan job `caksoria_{chat_id}` dan menghentikan sesi aktif.

### 2. Integrasi ke Router Handler: `bot/handlers/games.py`
- Menambahkan `"caksoria": "Caksoria"` ke `AVAILABLE_GAMES`.
- Menghubungkan routing perintah `/bermain`, `/atur`, `/status`, `/berhenti`, dan `/hasil`.
- Menambahkan `caksoria` ke penangkap pesan natural grup `process_game_message`.

### 3. Pengujian: `tests/test_caksoria.py`
- Pengujian CRUD konfigurasi `/atur caksoria`.
- Pengujian simulasi skenario persis permintaan user (delay 7 detik, keyword matching, user zoldy, dika, cecil, bena, abel, dan de-duplikasi pesan berulang).
- Seluruh 3 test case berhasil lolos 100%.

### 4. Dokumentasi: `docs/commands.md`
- Menambahkan perintah `/bermain caksoria` pada daftar mini-game.
