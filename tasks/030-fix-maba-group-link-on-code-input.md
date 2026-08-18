# 030 - Perbaikan Alur Link Grup MABA Saat Input Kode

## Apa yang Dikerjakan
Menambahkan pemanggilan fungsi `_mark_lengkapi_done_if_complete` pada _handler_ `INPUT_CODE` di `bot/handlers/messages.py` sesaat sebelum bot mengecek apakah data MABA sudah lengkap (`_is_lengkapi_done(prof_u)`).

## Mengapa Dikerjakan
Sebelumnya, MABA yang sudah mendaftar dan mengisi nama (melalui alur "Daftar Akun Mahasiswa Baru") belum dievaluasi kelengkapan datanya secara _flagging_ (kunci `_lengkapi_done` belum diset di _database_). Akibatnya, saat mereka menginput kode akses MABA, bot masih menganggap datanya belum lengkap dan menyuruh mereka mengetik `/lengkapi` kembali. Padahal, nama lengkap (sebagai satu-satunya field wajib MABA) sudah mereka isi di awal pendaftaran.

## Bagaimana Alur Kodenya Bekerja
1. Saat MABA menginput kode yang valid, perannya otomatis dikukuhkan (dan dialokasikan `maba_group`).
2. Tepat sebelum memeriksa apakah data MABA sudah lengkap, bot secara eksplisit memanggil `await _mark_lengkapi_done_if_complete(conn, db, uid)`.
3. Fungsi ini akan memeriksa `missing_required_fields`. Karena MABA sudah punya `full_name`, maka data dianggap lengkap dan kunci penanda (LENGKAPI_DONE_KEY) di profil akan diset menjadi `True`.
4. Setelah itu, pada blok pengecekan `if _is_lengkapi_done(prof_u):`, hasilnya akan bernilai `True`, sehingga bot akan langsung membuatkan undangan grup (_invite link_) dan tidak akan lagi menyuruh MABA mengetik `/lengkapi`.
