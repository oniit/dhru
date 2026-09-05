# Group Game Permissions

## Apa yang Dikerjakan
Mengimplementasikan fitur perizinan mini-games per grup secara dinamis. Menambahkan tabel `group_game_permissions` di database, command `/settings_game` untuk admin, dan validasi izin pada `/bermain`.

## Mengapa Dikerjakan
Sesuai permintaan pengguna agar game tidak terbuka untuk semua grup secara otomatis, melainkan harus dihidupkan (di-enable) oleh admin/owner masing-masing grup terlebih dahulu. Ini berguna untuk meminimalisir spam game di grup yang tidak menginginkannya.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Database Schema (`bot/database.py`)**:
   - Menambahkan tabel `group_game_permissions(chat_id, game_name, is_allowed)`.
   - Menambahkan _method_ `get_group_game_permissions`, `set_group_game_permission`, dan `is_game_allowed`.
2. **Handlers & Callback (`bot/handlers/games.py`)**:
   - Menambahkan command `/settings_game` yang merender sebuah `InlineKeyboardMarkup` dengan status (✅ / ❌) dari setiap game yang tersedia.
   - Command ini divalidasi agar hanya _owner_ atau admin grup yang dapat mengaksesnya menggunakan metode `_is_admin`.
   - Membuat *callback handler* `on_settings_callback` dengan rute `gamesettings:` untuk men-*toggle* izin game dan me-*refresh* _markup_ pesan.
3. **Validasi `/bermain` (`bot/handlers/games.py`)**:
   - Memodifikasi fungsi `cmd_bermain` sehingga akan melakukan pengecekan `is_game_allowed`.
   - Secara default (jika belum pernah disetting), nilai yang dikembalikan adalah `False` sehingga game ditolak, dan user harus mengaturnya terlebih dahulu.
4. **Registrasi Command (`bot/handlers/register.py`)**:
   - Mendaftarkan fungsi-fungsi baru tersebut pada *router/dispatcher*.
5. **Dokumentasi**:
   - Meng-update `docs/commands.md` dan `docs/database.md`.
