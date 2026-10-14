# Task 101: Validasi Instan Link LPM & Background Queue Tanpa Dependensi Userbot Wajib

## Deskripsi Singkat
Mengatasi masalah pengiriman perintah `/lpm` yang tidak memberikan respons balik atau validasi (stuck di status `PENDING`), kegagalan saat mendaftar Chāryārthī (`count_valid_promos < 1`), serta pencegahan pesan error "Link sudah pernah diklaim" pada link yang masih dalam antrean atau gagal sebelumnya.

## Masalah & Analisis
1. **Stuck Tanpa Respons**:
   - Ketika pengguna mengirim `/lpm <link>`, bot utama hanya mencatat link ke tabel `promo_verifications` dengan status `PENDING` dan menampilkan pesan "Sistem sedang memvalidasi pesanmu...".
   - Sistem validasi sebelumnya sepenuhnya bergantung pada script mikroservice Pyrogram eksternal (`checker.py`) yang berjalan secara terpisah.
   - Karena `checker.py` tidak sedang berjalan (dan sesi Pyrogram belum ter-otorisasi login nomor telepon), link promosi tetap berstatus `PENDING` tanpa ada notifikasi hasil validasi (sukses maupun gagal) yang dikirim ke pengguna.
2. **Terhambatnya Submit Pendaftaran**:
   - Pendaftaran Chāryārthī dan fitur terkait mewajibkan minimal 1 promo valid (`count_valid_promos >= 1`). Karena link tersangkut di `PENDING`, pengguna mendapat alert "Anda belum melakukan promosi atau sistem masih memvalidasinya".
3. **Deadlock "Link Sudah Pernah Diklaim"**:
   - `check_promo_link_exists` sebelumnya memeriksa apakah ada baris dengan `link` tersebut tanpa memfilter `status`. Akibatnya, jika link berstatus `PENDING` atau pernah gagal, pengguna diblokir permanen untuk mengirim ulang link yang sama.

## Solusi & Implementasi
1. **Public Embed Verification Engine di [`bot/handlers/promo.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/promo.py)**:
   - Membuat fungsi `verify_lpm_link_embed(conn, db, user_id, link, lpm_keyword)` yang mengambil dan mem-parsing widget embed publik Telegram (`https://t.me/<chat>/<msg_id>?embed=1`) secara asinkron menggunakan `httpx`.
   - Memvalidasi:
     - Eksistensi pesan publik.
     - Keberadaan kata kunci promosi (`lpm_keyword`, default: `"dhruva"`).
     - Kesesuaian identitas pengirim (username atau first_name) dengan akun utama pemohon atau Akun Kerja yang tertaut di `linked_accounts`.
   - Mengembalikan status `(is_valid, status_code, err_msg)`.

2. **Validasi Instan pada `/lpm` di [`bot/handlers/promo.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/promo.py)**:
   - Handler `lpm_cmd` langsung memicu `verify_lpm_link_embed`.
   - Jika valid: langsung mengupdate status menjadi `VALID`, menambahkan reward +1 Agra (`db.add_agra`), dan membalas chat secara instan: `"✅ Link LPM kamu berhasil divalidasi! ... Kamu mendapatkan +1 Agra."`.
   - Jika ada error definitif (seperti salah kata kunci atau salah pengirim): mengupdate status dan membalas dengan alasan spesifik kegagalan.
   - Jika terjadi kendala jaringan: link tetap `PENDING` untuk diproses oleh antrean background.

3. **Background Processing Queue di [`bot/jobs.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/jobs.py)**:
   - Menambahkan fungsi `process_promo_queue` yang dijadwalkan berjalan berulang setiap 10 detik (`jq.run_repeating(process_promo_queue, interval=10, first=5)`).
   - Memproses setiap baris `promo_verifications` yang berstatus `PENDING`, memberikan reward Agra, dan mengirimkan pesan notifikasi ke pengguna secara otomatis.

4. **Pembaruan Skema Pengecekan di [`bot/database.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/database.py)**:
   - Mengubah `check_promo_link_exists` agar hanya mengembalikan `True` jika link berstatus `VALID`.
   - Menambahkan `get_promo_link_record(conn, link)`.
   - Mengubah `add_promo_verification` sehingga jika link sudah ada (misal sebelumnya gagal atau pending), baris diperbarui kembali ke `PENDING` alih-alih melempar error duplikasi.
