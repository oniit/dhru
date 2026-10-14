# Task 100: Ketahanan Koneksi Turso Database & Penanganan Error Update

## Deskripsi Singkat
Mengatasi masalah kegagalan koneksi berkala (_transient disconnect / keep-alive socket drop_) ke remote database Turso pada `AiosqliteConnectionMock`, melindungi rantai eksekusi _update handler_ di `global_profile_tracker` dari _unhandled exception_, serta mendaftarkan handler error terpusat pada `Application` Telegram.

## Masalah & Analisis
1. **Turso Connection Drop**:
   - `libsql_client` berjalan menggunakan `aiohttp.ClientSession` yang menyimpan _connection pool_ TCP HTTP/1.1 _keep-alive_.
   - Ketika bot berada dalam kondisi _idle_ tanpa kueri database selama beberapa saat (hanya melakukan polling update Telegram dan interval scheduler kosong), proxy remote Turso/Cloudflare menutup koneksi TCP secara sepihak.
   - Saat update baru masuk, kueri database pertama mencoba menggunakan koneksi _idle_ yang sudah mati dari pool, sehingga `aiohttp` mengalami kegagalan pada `await resp.start(conn)` (`ServerDisconnectedError` / `ClientOSError`).
   - `AiosqliteConnectionMock` sebelumnya tidak memiliki mekanisme _auto-retry_ untuk _transient socket error_, menyebabkan eksekusi langsung melempar _exception_.

2. **Middleware Halt di `global_profile_tracker`**:
   - `global_profile_tracker` berjalan pada `group=-1` sebelum handler utama (`group=0, 1, 2`) dieksekusi.
   - Operasi `db.sync_user_basic_info` tidak dibungkus dalam blok `try...except`.
   - Ketika error koneksi Turso terjadi, PTB menghentikan pemrosesan update tersebut, sehingga perintah atau pesan yang dikirim pengguna ter-drop dan tidak diproses.
   - Selain itu, cache in-memory `cache[u.id] = current_info` diatur sebelum kueri berhasil. Jika kueri gagal, cache telanjur tersimpan sehingga sinkronisasi profil user tersebut tidak pernah diulang.

3. **Peringatan Missing Error Handler**:
   - PTB mencatat log: `No error handlers are registered, logging exception` karena `Application` belum mendaftarkan callback `add_error_handler`.

## Solusi & Implementasi
1. **Auto-Retry & Client Recreation di [`bot/database.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/database.py)**:
   - Menambahkan fungsi pembantu `_is_transient_db_error(e)` untuk mendeteksi error koneksi jaringan (`aiohttp.ClientError`, `ServerDisconnectedError`, `ClientOSError`, `ConnectionResetError`, `TimeoutError`).
   - Menambahkan mekanisme _auto-retry_ hingga 3 kali dengan backoff bertahap (`0.3s * attempt`) pada method `execute`, `executemany`, dan `executescript`.
   - Pada percobaan kedua jika masih gagal dan kredensial tersedia, client `libsql_client` akan di-close dan dibuat ulang secara otomatis (`_recreate_client`).
   - Menyimpan `url` dan `auth_token` di instance `AiosqliteConnectionMock`.

2. **Isolasi Resilient di [`bot/handlers/messages.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/messages.py)**:
   - Membungkus pemanggilan `db.sync_user_basic_info` di dalam blok `try...except Exception as e:` dengan pencatatan `log.warning`.
   - Memperbarui `cache[u.id] = current_info` hanya setelah kueri berhasil.
   - Memastikan `global_profile_tracker` tidak pernah melempar exception keluar, sehingga rantai pemrosesan update pengguna selalu berlanjut normal ke handler berikutnya.

3. **Registrasi Error Handler Terpusat di [`main.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/main.py)**:
   - Membuat fungsi `error_handler(update: object, context: ContextTypes.DEFAULT_TYPE)` yang mencatat exception secara komprehensif.
   - Mendaftarkannya ke instance `Application` melalui `application.add_error_handler(error_handler)`.

4. **Pembersihan Sesi Klien pada Tes di [`tests/test_chat_command.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_chat_command.py)**:
   - Membungkus eksekusi tes dalam blok `try...finally: await conn.close()` agar tidak menyisakan *unclosed client session / connector*.
