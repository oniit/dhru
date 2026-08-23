# Task 040: Dynamic Promo Menu & Story Checker

## Deskripsi
Menambahkan fitur pengaturan dinamis untuk sistem promosi (LPM) dan validasi Story Telegram secara terpusat dari bot via perintah `/promo`. Sebelumnya, kata kunci LPM ("dhruva") di-_hardcode_ di `checker.py`. Kini Owner dapat menggantinya melalui antarmuka Telegram, dan fitur baru untuk memvalidasi _repost_ di Story Telegram juga telah ditambahkan.

## Alasan
Kebutuhan Owner untuk mengubah syarat promosi (kata kunci) dan postingan referensi yang harus di-_repost_ ke Story tanpa perlu mengedit kode sumber dan melakukan _restart_ berulang kali. Ini memungkinkan event promosi yang lebih dinamis.

## Perubahan Teknis
1. **Skema Database (`bot/database.py`)**
   - Menambahkan tabel `bot_settings` (`setting_key`, `setting_value`) untuk menyimpan `promo_lpm_keyword` dan `promo_story_post`.
   - Modifikasi `promo_verifications` dengan penambahan kolom `promo_type` (`lpm` atau `story`).
   - Penambahan helper method `get_setting` dan `set_setting`.
2. **Command Handlers (`bot/handlers/promo.py`)**
   - Penambahan `/promo` untuk memunculkan _Inline Keyboard_ bagi Owner.
   - Penambahan _Callback_ dan _Message Handler_ berbasis _state_ (disimpan di `context.user_data["promo_state"]`) untuk menerima _input_ Owner.
   - Penambahan `/story <link>` agar pengguna bisa mendaftarkan link story Telegram mereka.
3. **Userbot Checker (`checker.py`)**
   - Skrip tidak lagi menggunakan kata "dhruva" secara *hardcode*, melainkan _fetch_ konfigurasi dari database via `get_setting("promo_lpm_keyword")`.
   - Menambahkan _branch_ pengecekan untuk `promo_type == 'story'`.
   - Menggunakan `app.get_stories()` untuk mengekstrak story dan melakukan iterasi ke `.media_areas` untuk mencari tipe _channel post_.
   - Melakukan perbandingan `channel_id` dan `message_id` target konfigurasi dari `promo_story_post`.
   - Memberikan *reward* +3 Agra untuk validasi Story yang berhasil (dibandingkan dengan +1 Agra untuk LPM biasa).
   - "Akun Kerja" (Linked Accounts) tetap dapat digunakan untuk menyetor link Story, sama seperti LPM.
