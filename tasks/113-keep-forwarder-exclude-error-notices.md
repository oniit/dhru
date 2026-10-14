# 113 - Exclude Bot Error & Status Notices in Daily KEEP to POST Forwarder

## Ringkasan
Menyederhanakan dan memperketat logika filter pada job harian pukul 15:00 WIB (`daily_keep_to_post`) di `bot/jobs.py`:
- **Semua pesan apapun di KEEP** (teks, foto, video, album, dokumen, poll, audio, VN, stiker, kontak, lokasi, dll) **wajib diforward** ke Channel POST (`POST_CH_ID`).
- **Satu-satunya yang di-exclude** adalah:
  1. Pesan dari bot (`from_user.is_bot` atau ID bot dari `BOT_TOKEN`).
  2. Dua template notifikasi spesifik yang diproduksi oleh bot ini sendiri di channel KEEP (`"cek @dhruvaposter"` untuk pesan sukses dan `"terjadi kesalahan saat mem-forward pesan"` untuk pesan gagal).
  3. Pesan servis Telegram (`msg.service`, seperti pin pesan atau ubah foto channel) dan pesan kosong (`msg.empty`).

## Alasan & Akar Masalah
Sebelumnya, jika channel KEEP sedang kosong atau hanya tersisa pesan notifikasi error dari hari sebelumnya, pesan error Pyrogram `[400 MESSAGE_ID_INVALID]` tidak terfilter dan ikut dimasukkan ke antrean forward. Akibatnya Pyrogram mencoba mem-forward pesan error itu sendiri sehingga melempar error `MESSAGE_ID_INVALID` berulang setiap hari. Pengecekan teks kini disederhanakan murni pada 2 kalimat template asli buatan bot ini tanpa menebak-nebak kata kunci asing, menghilangkan potensi *false positive* terhadap postingan pengguna.

## Perubahan Teknis
- **`bot/jobs.py` (`is_keep_msg_excluded`)**:
  - Menghapus daftar tebakan kata kunci acak; diganti dengan pengecekan langsung terhadap 2 template pasti bot ini (`"cek @dhruvaposter"` atau `"terjadi kesalahan saat mem-forward pesan"`).
  - Mengecek identitas bot (`from_user.is_bot` dan kecocokan ID bot).
  - Menjaga proteksi *batch chunking* (100 pesan) dan fallback single-message forwarding jika salah satu ID pesan sudah kadaluarsa/dihapus oleh TTL Telegram.
- **`tests/test_keep_forwarder.py`**:
  - Menguji variasi pesan: teks normal, foto berketerangan, polling tanpa teks, pesan bot (objek user dan teks template sukses/gagal), pesan kosong, dan pesan servis Telegram. Seluruh pengujian lolos 100%.


