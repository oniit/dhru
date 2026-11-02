# Task 134: Remote Greeting Support, Rich Placeholders, and HTML Formatting Guide

## Ringkasan Perubahan
Memperbarui fitur ucapan selamat datang anggota baru (`/setgreeting` dan `/greeting`) agar dapat dikonfigurasi secara remote (lintas grup dan dari Private Chat / PM Bot) dengan tetap mempertahankan kompatibilitas 100% terhadap format lama di dalam grup (*backward-compatible*). Selain itu, sistem kini mendukung placeholder yang jauh lebih lengkap, auto-sanitasi karakter ampersand (`&`), validasi sintaks HTML bawaan, serta panduan interaktif lengkap yang mencantumkan daftar ID grup aktif.

---

## Latar Belakang & Alasan
1. **Kebutuhan Konfigurasi Fleksibel (Remote)**: Sebelumnya, `/setgreeting` hanya bisa dijalankan di dalam grup target (`chat.type in ('group', 'supergroup')`). Hal ini menyulitkan admin atau owner bot yang ingin menyetel pesan sambutan dari obrolan pribadi (PM Bot) agar tidak mengotori obrolan publik di grup.
2. **Keterbatasan Placeholder**: Sebelumnya hanya tersedia `{name}` (yang hanya mengambil nama depan) dan `{username}`. Pengguna membutuhkan placeholder yang lebih lengkap seperti mention langsung yang dapat diklik (`{mention}`), nama lengkap (`{full_name}`), nama depan (`{first_name}`), nama belakang (`{last_name}`), nama grup (`{chat_title}`), dan ID pengguna (`{id}`).
3. **Pencegahan Error Formatting HTML**: Pengiriman pesan sambutan menggunakan mode HTML Telegram (`parse_mode="HTML"`). Jika admin memasukkan tag HTML yang tidak ditutup atau menyertakan karakter reserved seperti `&` tanpa di-*escape*, bot akan gagal mengirimkan pesan ucapan selamat datang ketika ada anggota baru yang bergabung.

---

## Alur Teknis & Implementasi

### 1. Helper Format & Validasi (`bot/handlers/common.py`)
- **`TelegramHTMLValidator(HTMLParser)`**: Memeriksa tag yang diizinkan oleh Telegram (`<b>`, `<i>`, `<u>`, `<s>`, `<a>`, `<code>`, `<pre>`, `<tg-spoiler>`, dll), memeriksa tag penutup yang seimbang, dan memastikan tag `<a>` memiliki atribut `href`.
- **`sanitize_telegram_html(text)`**: Mengubah karakter `&` yang berdiri sendiri menjadi `&amp;` secara otomatis tanpa merusak entitas yang sudah valid (`&amp;`, `&lt;`, `&gt;`, `&#123;`, dll).
- **`render_greeting_message(template, user, chat_title)`**:
  - Mereplace seluruh placeholder yang didukung secara aman dengan `html.escape` pada data pengguna/grup untuk mencegah *HTML injection*.
  - Placeholder yang didukung:
    - `{name}` / `{full_name}`: Nama lengkap member baru.
    - `{first_name}`: Nama depan.
    - `{last_name}`: Nama belakang.
    - `{username}`: `@username` jika ada, atau nama jika tidak memiliki username.
    - `{mention}`: Tautan tag/mention langsung ke profil pengguna (`<a href="tg://user?id=...">Nama</a>`).
    - `{chat_title}` / `{title}`: Judul grup.
    - `{id}` / `{user_id}`: Telegram User ID.
- **`validate_greeting_html(template)`**: Melakukan simulasi render template dengan user dummy lalu memvalidasi struktur HTML yang dihasilkan sebelum disimpan ke database.

### 2. Peningkatan Database (`bot/database.py`)
- Memperbarui fungsi `update_greeting_message(conn, chat_id, greeting_message, title=None)` agar menggunakan pola `INSERT INTO bot_chats ... ON CONFLICT(chat_id) DO UPDATE SET ...`. Hal ini memastikan bahwa target grup yang baru pertama kali disetel greeting-nya via remote tetap tersimpan dengan aman meskipun entri grup tersebut belum pernah ter-insert sebelumnya.

### 3. Logika Perintah `/setgreeting` & `/greeting` (`bot/handlers/commands.py`)
- **Deteksi Argumen Pintar (*Smart Parsing*)**:
  - Menginspeksi token pertama setelah perintah. Jika berupa integer negatif (`val < 0`), maka dianggap sebagai `target_chat_id` (mode remote).
  - Jika bukan integer negatif dan perintah dipanggil di dalam grup, maka otomatis menargetkan grup saat ini (mode lokal/lama).
  - Jika dipanggil di Private Chat tanpa ID grup tujuan, bot memberikan pesan peringatan dan panduan.
- **Pengecekan Otorisasi**:
  - Owner / Admin / Internal bot memiliki wewenang remote ke seluruh grup.
  - Pengguna biasa / Admin grup diverifikasi statusnya pada grup target melalui `context.bot.get_chat_member(target_chat_id, user.id)`. Hanya `creator` dan `administrator` di grup target yang diizinkan menyetel greeting untuk grup tersebut.
- **Panduan Interaktif (`/setgreeting help` atau tanpa argumen)**:
  - Menampilkan panduan lengkap sintaks perintah, daftar placeholder, tag format HTML, dan contoh pesan siap pakai.
  - Menyertakan daftar grup aktif yang terdaftar di bot (`bot_chats`) beserta ID grupnya agar admin mudah melakukan *copy-paste* ID target.
- **Pratinjau Langsung**:
  - Setiap kali berhasil menyetel atau mengecek pesan dengan `/setgreeting` atau `/greeting`, bot langsung menampilkan teks template asli beserta *live preview* dengan formatting HTML yang aktif.

### 4. Eksekusi Pengiriman Sambutan (`bot/handlers/messages.py`)
- Pada fungsi `on_chat_member`:
  - Menggunakan `render_greeting_message` untuk merender template ucapan selamat datang secara seragam.
  - Menambahkan *try-except fallback*: jika pengiriman dengan `parse_mode="HTML"` gagal karena alasan tak terduga, bot melakukan *fallback* dengan mengirimkannya sebagai plain text agar ucapan selamat datang tetap terkirim ke anggota baru.

---

## Pengujian & Verifikasi
- Dibuat unit test komprehensif di `tests/test_greeting.py` dengan 12 test case:
  - Verifikasi semua placeholder ter-render dengan benar.
  - Verifikasi fallback nama ketika user tidak memiliki username.
  - Verifikasi sanitasi XSS/karakter reserved pada nama user.
  - Verifikasi auto-escape ampersand (`&` -> `&amp;`).
  - Verifikasi validator HTML (tag tidak tertutup, tag terlarang, link tanpa href).
  - Verifikasi panduan bantuan `/setgreeting help`.
  - Verifikasi pengaturan di dalam grup (backward compatibility).
  - Verifikasi pengaturan remote dari private chat.
  - Verifikasi mematikan greeting remote (`off`).
  - Verifikasi penolakan akses untuk user yang bukan admin grup target.
  - Verifikasi pratinjau `/greeting`.
  - Verifikasi penanganan `on_chat_member` saat ada member baru masuk.
- Seluruh 12 test suite di `tests/test_greeting.py` lulus 100% (`12 passed in 0.70s`).
- Pengujian regresi pada `tests/test_messages_chunking.py` juga lulus 100% (`5 passed in 0.69s`).

