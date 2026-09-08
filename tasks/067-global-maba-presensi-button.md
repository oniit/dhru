# Task: Add Hadir Button to Global Maba Presensi Message

## Latar Belakang
User meminta agar presensi Maba yang dikirimkan ke grup general juga memunculkan tombol "✅ Hadir", sehingga maba bisa melakukan presensi cukup dengan satu kali klik dari grup mana saja (baik grup general maupun grup kelompoknya masing-masing). User juga merevisi bahwa ID grup "general" untuk maba bukanlah `PRESENCE_CH_ID` melainkan `OSPEK_GID`.

## Pekerjaan yang Dilakukan
- Menambahkan konfigurasi bacaan `OSPEK_GID` di `bot/settings.py` yang diambil dari berkas `.env`.
- Mengubah target pengiriman pesan _master global_ pada fungsi `daily_maba_attendance_open` (`bot/jobs.py`) dari yang sebelumnya menggunakan `PRESENCE_CH_ID` menjadi `OSPEK_GID`.
- Menambahkan `reply_markup` berisi `InlineKeyboardMarkup` dengan tombol "✅ Hadir" (callback data `sh:{sid}`) ke pengiriman pesan awal saat sesi presensi `maba_auto` dibuka di `bot/jobs.py`.
- Memodifikasi `refresh_maba_presensi_announcement` di `bot/handlers/attendance.py` agar pembaruan pesan (edit message text) di master message global juga selalu melampirkan tombol "✅ Hadir" jika sesinya belum ditutup. 

## Teknis
- Pada fungsi `daily_maba_attendance_open` (`bot/jobs.py`), presensi Maba kini diarahkan ke `OSPEK_GID` alih-alih `PRESENCE_CH_ID`. Variabel `kb` disisipkan pada argumen `reply_markup=kb` untuk pengiriman pesan ke `OSPEK_GID`.
- Mengambil nilai `OSPEK_GID` dari environment variable di `bot/settings.py`.
- Pada fungsi `refresh_maba_presensi_announcement` (`bot/handlers/attendance.py`), blok `# 1. Update Global Master Message` kini membuat variabel `kb_global` apabila belum `closed`, dan menambahkannya sebagai `reply_markup` ke `await context.bot.edit_message_text`.
- Handler callback data `sh:` sebelumnya sudah didesain bisa menerima klik dari Maba untuk session `maba_auto`, sehingga tidak ada modifikasi logic yang diperlukan lagi di level callback.
