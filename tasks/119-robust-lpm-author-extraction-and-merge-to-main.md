# 119 - Robust LPM Author Extraction & Merge to Main

## Deskripsi Singkat
Menyempurnakan ekstraksi pengirim pesan Telegram (author username & author name) pada validasi promosi LPM publik di `bot/handlers/promo.py` agar tangguh terhadap variasi respons HTML widget Telegram, menambahkan fallback `NETWORK_ERROR` (antrean latar belakang userbot MTProto) ketika Telegram menganonimkan author, serta menyiapkan penggabungan seluruh branch rilis teruji (`release-audit`) ke branch `main`.

---

## Masalah & Penyebab
1. **Kegagalan Ekstraksi Author pada Telegram Web Embed**:
   - Telegram widget (`https://t.me/<group>/<msg_id>?embed=1`) menyajikan link username pengirim baik di link teks (`tgme_widget_message_author_name`) maupun di avatar pengguna (`tgme_widget_message_user`).
   - Namun, saat Telegram merender pengirim dengan inner span bertingkat `<span class="tgme_widget_message_author_name"><span dir="auto">...</span></span>`, regex sebelumnya memotong parsing pada tag penutup pertama, menghasilkan author name string kosong (`""`).
2. **Anonisasi Telegram pada Akses Berulang (Rate Limiting/Privacy)**:
   - Jika Telegram mengembalikan widget dalam status anonim (menghapus atribut nama dan username pengirim), sistem sebelumnya secara keliru menganggapnya sebagai `SENDER_MISMATCH` (akun salah), padahal bot belum mengetahui siapa pengirim aslinya.
3. **Kerapuhan Unit Test LPM**:
   - `tests/test_promo_lpm.py` melakukan hit langsung ke endpoint publik Telegram (`https://t.me/sirkuse/27`), yang rentan mengalami flakiness / anonisasi akibat throttling IP dari Telegram saat pengujian dijalankan.

---

## Solusi & Implementasi Teknis
1. **Robust Extraction di `bot/handlers/promo.py`**:
   - Menambahkan ekstraksi fallback untuk `author_username` dari elemen avatar `.tgme_widget_message_user a[href]` jika link nama pengirim tidak tersedia.
   - Menggunakan parsing blok kontainer `.tgme_widget_message_author` untuk mengekstrak `author_name` secara menyeluruh dengan membuang tag HTML bersarang.
   - Jika post ditemukan dan memuat kata kunci promosi yang benar, namun Telegram menganonimkan atribut pengirim (`not author_username and not author_name`), sistem mengembalikan `NETWORK_ERROR` alih-alih `SENDER_MISMATCH`. Hal ini memungkinkan request beralih ke antrean `PENDING` agar diverifikasi oleh MTProto *userbot* (`checker.py`) sesuai panduan arsitektur IPC.
2. **Determinisme Unit Testing**:
   - Memperbarui `tests/test_promo_lpm.py` dengan mock respons embed Telegram yang deterministik dan memverifikasi seluruh skenario pengujian tanpa terpengaruh pembatasan jaringan Telegram.
3. **Regresi Penuh**:
   - Menjalankan seluruh test suite (`pytest`) dengan 39 skenario pengujian berhasil lulus 100%.
