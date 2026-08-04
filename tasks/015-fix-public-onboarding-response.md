# Perbaikan Respons Onboarding Akun Publik

## Deskripsi Bug
Ditemukan bahwa akun tipe `public` tidak mendapatkan balasan apa-apa (bot diam atau _no response_) setelah diarahkan untuk mengisi nama lengkap.

## Analisis Penyebab
- Pengecekan awal menunjukkan bahwa logika `TEXT_LC:` untuk menangkap pengisian profil sebenarnya sudah benar dan berjalan.
- Masalah terletak pada _UnboundLocalError_ di dalam `bot/handlers/messages.py`. 
- Terdapat impor variabel bayangan (_shadowing_) secara lokal di baris 185: `from bot.handlers.commands import _is_lengkapi_done`. Karena struktur _scoping_ Python, impor dalam suatu _if statement_ ini memaksa _interpreter_ menjadikan `_is_lengkapi_done` sebagai variabel lokal untuk keseluruhan fungsi `on_private_message`.
- Ketika alur eksekusi lompat langsung ke baris 266 untuk pendaftaran publik, baris 185 dilewati sehingga variabel lokal tersebut belum terdefinisi (belum diinisialisasi), menyebabkan _UnboundLocalError_ senyap yang merusak _event loop_ dan mencegah pengiriman pesan balasan.

## Aktivitas Perbaikan
- Menghapus impor `_is_lengkapi_done` yang membayang (_shadowing_) pada `bot/handlers/messages.py`.
- Memastikan metode pendaftaran untuk memanggil `_is_lengkapi_done` yang sudah terdefinisi secara global di pucuk file `messages.py`.
- Melakukan pengetesan menggunakan _script simulasi_ (`test_public_onboarding.py`) dan memastikan respons sukses berbunyi "✨ Terima kasih. Data awal Anda..." sekarang tampil dengan aman.

## Status
- **Fixed**: Skema _Onboarding_ dan `/lengkapi` untuk role `public` (dan role-role lain) beroperasi kembali tanpa kesalahan _UnboundLocalError_.
