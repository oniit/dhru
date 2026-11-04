# Task 135: Fix Greeting Bugs, Support Native Telegram Formatting, and Privacy Hardening

## Ringkasan Perubahan
Memperbaiki sejumlah bug dan kelemahan logika pada fitur ucapan selamat datang (`/setgreeting`, `/greeting`, dan event `on_chat_member`):
1. **Dukungan Format Bawaan Telegram (*Native Text Formatting*)**: Bot kini mengenali teks yang diformat langsung menggunakan UI bawaan Telegram (blok teks lalu pilih Tebal, Miring, Coret, Underline, Spoiler, atau Link) dan otomatis mengonversinya menjadi entitas HTML valid tanpa merusak tampilan.
2. **Pencegahan Entity Parse Error pada HTML**: Memperbaiki validasi HTML agar mendeteksi karakter `<` yang bukan tag (misal emotikon `<3` atau perbandingan angka) serta membungkus pratinjau `/setgreeting` dan `/greeting` dengan blok *fallback plain text* agar bot tidak pernah melempar *uncaught exception* jika Telegram menolak entitas.
3. **Proteksi Privasi & Kebocoran Daftar Grup di Ruang Publik**: Pesan bantuan `/setgreeting help` di dalam grup publik kini tidak lagi membocorkan daftar grup eksternal bot. Daftar grup hanya ditampilkan jika dipanggil dari *Private Chat* (PM) oleh Owner/Admin Bot.
4. **Pencegahan FloodWait & Latensi**: Menghilangkan loop pengecekan hak akses `get_chat_member` beruntun (hingga 15x) untuk user non-admin di obrolan pribadi, menggantikannya dengan instruksi terarah.
5. **Validasi ID Grup Sasaran yang Lebih Ketat**: Nilai integer negatif seperti `-10` pada kalimat (contoh: `/setgreeting -10 poin jika melanggar`) tidak lagi dianggap sebagai `target_chat_id` palsu.
6. **Single-Pass Placeholder Replacement**: Penggantian placeholder di `render_greeting_message` kini menggunakan regex satu arah (*single-pass*) yang kebal terhadap *cascading placeholder injection*, mendukung variasi penulisan `@{username}` tanpa menghasilkan `@` ganda (`@@username`), dan *case-insensitive* (`{Name}`, `{Chat_Title}`).
7. **Penyaringan Bot**: Menambahkan pengecekan `if new_member.user.is_bot: return` pada `on_chat_member` agar bot tidak lagi menyapa bot lain yang diundang ke dalam grup.

---

## Alur Teknis & Implementasi

### 1. Ekstraksi Format Bawaan Telegram (`bot/handlers/common.py`)
- Menambahkan fungsi helper `extract_greeting_source_from_message(message)`:
  - Memeriksa apakah `message.entities` memuat entitas format visual bawaan Telegram (`BOLD`, `ITALIC`, `UNDERLINE`, `STRIKETHROUGH`, `SPOILER`, `TEXT_LINK`, dll).
  - Jika ada, bot mengekstrak teks dari `message.text_html` sehingga formatting bawaan langsung dikonversi menjadi tag HTML Telegram yang valid secara otomatis, dan karakter reserved seperti `<3` atau `&` otomatis di-*escape* dengan aman.
  - Jika tidak ada, bot menggunakan `message.text` dan melakukan sanitasi HTML manual / auto-escape jika teks polos.

### 2. Single-Pass Placeholder Substitution (`bot/handlers/common.py`)
- Mengganti pemanggilan rantai `.replace()` berturut-turut pada `render_greeting_message` dengan pencocokan regex:
  `re.sub(r'@?\{([a-zA-Z0-9_]+)\}', _replacer, template)`
- Mendukung:
  - `{name}` / `{full_name}`, `{first_name}`, `{last_name}`, `{chat_title}`, `{id}`
  - `{username}` dan `@{username}`: Jika user memiliki username, otomatis menghasilkan `@username` (tanpa duplikasi `@`). Jika user tidak memiliki username, menghasilkan nama lengkap tanpa menyisakan karakter `@` liar.
  - Mencegah injection apabila nama member Telegram memuat string placeholder seperti `{chat_title}`.

### 3. Pengetatan Validasi HTML & Fallback UI (`bot/handlers/common.py` & `bot/handlers/commands.py`)
- Memperbarui `TelegramHTMLValidator` agar membersihkan tag resmi terlebih dahulu menggunakan `HTML_TAG_PATTERN.sub('', text)`. Jika masih ada sisa karakter `<`, validator melempar pesan kesalahan yang ramah dan memandu user menggunakan format bawaan atau `&lt;`.
- Membungkus pemanggilan `update.message.reply_text(..., parse_mode="HTML")` pada `cmd_set_greeting` dan `cmd_greeting` dengan `try...except`. Jika terjadi kegagalan parse dari Telegram, bot mengirimkan template tersimpan sebagai plain text beserta pesan peringatan, mencegah unhandled crash.

### 4. Proteksi Kebocoran Grup & Eliminasi Polling API Telegram (`bot/handlers/commands.py`)
- Memperbarui parameter `build_greeting_help_text` dengan `is_private_chat` dan `current_chat`.
- Jika dipanggil di dalam grup (`not is_private_chat`), bantuan hanya menampilkan ID grup saat ini (`📌 Grup Saat Ini: Nama Grup (chat_id)`).
- Jika dipanggil di *Private Chat* oleh non-admin bot, bot tidak lagi memanggil API Telegram 15 kali untuk memindai keanggotaan grup, melainkan memberikan panduan format remote.

### 5. Filter Bot pada Event Anggota Baru (`bot/handlers/messages.py`)
- Pada handler `on_chat_member`:
  ```python
  if getattr(new_member.user, "is_bot", False):
      return
  ```
  Memastikan bot pembantu/moderasi lain yang ditambahkan ke grup tidak mendapatkan pesan ucapan selamat datang.

---

## Verifikasi Pengujian
Semua pengujian unit test di `tests/test_greeting.py` bertambah dari 12 menjadi 18 test suite dan lulus 100%:
- `test_render_greeting_message_single_pass_no_cascade` ✅
- `test_render_greeting_message_handles_at_username` ✅
- `test_validate_greeting_html` (termasuk deteksi karakter `<` tanpa tag) ✅
- `test_cmd_set_greeting_preserves_native_telegram_formatting` ✅
- `test_cmd_set_greeting_help_in_group_does_not_leak_other_groups` ✅
- `test_cmd_set_greeting_negative_number_not_treated_as_chat_id` ✅
- `test_on_chat_member_ignores_bot` ✅

Pengujian regresi pada `tests/test_messages_chunking.py` juga lulus 100% (5 passed).

