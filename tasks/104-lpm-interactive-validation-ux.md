# Task 104: Interactivity & Feedback Respons Validasi Link LPM (/lpm)

## Deskripsi Singkat
Meningkatkan User Experience (UX) pada perintah `/lpm <link>` dengan menambahkan balasan awal status sedang diproses (waiting message), penyempurnaan pesan kegagalan/validasi spesifik yang komprehensif, serta penanganan error teknis agar pengguna selalu mendapatkan kepastian informasi responsif secara instan dan tidak mengalami kondisi tanpa balasan ("senyap").

## Masalah & Analisis
1. **Ketiadaan Umpan Balik Awal (No Waiting Feedback)**:
   - Pada versi sebelumnya, saat user mengeksekusi `/lpm <link>`, bot langsung melakukan request HTTP `httpx.get` ke widget embed Telegram publik tanpa mengirim pesan pendahulu.
   - Jika koneksi jaringan sedang lambat, bot tampak tidak merespons sama sekali, menimbulkan keraguan apakah perintah diterima atau tidak.
2. **Ketiadaan Notifikasi jika Terjadi Exception**:
   - Jika terjadi kendala tak terduga (misalnya format embed tidak lazim, parse error, atau glitch database), fungsi tidak terbungkus exception handling khusus dengan balasan ke pengguna, sehingga tidak ada balasan sama sekali ke chat pengguna.
3. **Penyempurnaan Regex & Identitas Pengirim (Author Matching)**:
   - Widget embed Telegram terkadang merender nama pengirim di dalam tag `<span>` atau `<div>` tanpa tag `<a>` jika akun pengirim tidak memiliki username publik. Regex sebelumnya hanya mencari tag `<a>` sehingga pengirim tanpa username berpotensi gagal dikenali (`SENDER_MISMATCH`).
   - Ekstraksi pengirim kini diperluas untuk mencakup `full_name` dari profil user dan nama dari linked account (`linked_accounts`).

## Solusi & Implementasi
1. **Pesan Progres Interaktif di [`bot/handlers/promo.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/promo.py)**:
   - Ketika `/lpm <link>` dijalankan, bot langsung mengirimkan pesan:
     `⏳ Sedang Memvalidasi Link LPM...\nSistem sedang memeriksa postingan promosi Anda ke server Telegram. Mohon tunggu sebentar...`
   - Setelah validasi selesai, pesan tersebut di-edit (`_safe_edit_or_reply`) dengan status definitif:
     - **Sukses**: `✅ Link LPM Berhasil Divalidasi! (+1 Agra)`
     - **Gagal Validasi**: `❌ Gagal Memvalidasi Link LPM` beserta rincian `Alasan:` spesifik (kata kunci tidak cocok, pesan tidak ditemukan, bukan akun pengirim terdaftar).
     - **Grup Private**: `❌ Grup Private Tidak Didukung` dengan penjelasan bahwa link harus dari grup publik.
     - **Jaringan Lambat / Queue**: `⏳ Pemeriksaan Instan Tertunda` dengan konfirmasi bahwa link telah masuk antrean latar belakang dan saldo akan otomatis bertambah jika valid.
     - **Error Teknis (Exception)**: `⚠️ Terjadi Kendala Teknis Saat Memvalidasi` dengan mencantumkan detail kendala dan menjamin link tetap aman di antrean.
2. **Perbaikan Parsing Embed & Author Matching**:
   - Menangani pengirim baik yang memiliki tag link `<a>` maupun elemen text author `<span>`/`<div>`.
   - Mengikutsertakan pengecekan `full_name` dari profil `profile_json` untuk akun utama dan linked accounts.
3. **Penyempurnaan Notifikasi Background Queue di [`bot/jobs.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/jobs.py)**:
   - Menggunakan HTML parse mode yang aman (`html.escape`) dan menonaktifkan web preview tautan agar tampilan chat tetap ringkas dan rapi.
