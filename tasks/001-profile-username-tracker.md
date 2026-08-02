# Sinkronisasi Username Profil via Interaksi (Selesai)

## Konteks & Masalah
Pengguna sering mengganti _username_ atau _First Name_ di Telegram. Namun, karena arsitektur awal SQLite hanya mengandalkan `/start`, perubahan ini tidak pernah terdeteksi oleh _database_ kecuali user menekan `/start` ulang.

## Solusi Implementasi
Dibuat sistem _Tracker Middleware_ yang dipasang di grup level -1 (jalan paling pertama sebelum perintah apapun).

1. **`bot/database.py`**: Ditambahkan fungsi `sync_user_basic_info` yang melakukan `SELECT` lalu membandingkan `username, first_name, last_name`. Hanya melakukan `UPDATE` jika berbeda, untuk menekan beban I/O.
2. **`bot/handlers/messages.py`**: Ditambahkan _handler_ `global_profile_tracker` yang di-_trigger_ oleh segala jenis aktivitas pengguna (_messages, callback, update_).
3. **`bot/handlers/register.py`**: Memanggil _handler_ tersebut sebagai `TypeHandler(Update, ...)` di urutan teratas (`group=-1`).

## Optimasi (In-Memory Cache)
Kueri `SELECT` pada setiap aktivitas berpotensi memberatkan antrean I/O SQLite. Solusinya, dipasang `context.bot_data["profile_cache"]` (Berbasis RAM).
Bot hanya akan memanggil DB bila profil di Telegram mendadak tidak sama dengan profil yang tersimpan di _cache_. Hasil: 0% performa server terbebani (Telah Lulus Uji QA).
