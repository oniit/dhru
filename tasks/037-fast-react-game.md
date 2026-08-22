# Task 037: Implementasi Game Adu React

## Deskripsi
Deploy mini-game baru "Adu React" (Fast React) yang diadaptasi dari referensi `example.py`. Berbeda dari kode contoh yang menggunakan in-memory state, game ini diintegrasikan langsung dengan arsitektur bot yang ada (menggunakan database SQLite untuk sesi game) sehingga lebih andal dan sejalan dengan standar bot.

## Tujuan
- Memungkinkan admin/pemain di grup untuk berlomba-lomba memberikan react terbanyak ke sebuah pesan.
- Menggunakan database untuk menyimpan sesi permainan.
- Memproses `MessageReactionUpdated` via API Telegram.

## Perubahan Kode
1. **`bot/games/adu_react.py`**:
   - Membuat modul game baru.
   - Mengimplementasikan alur: `/bermain adu_react`, `/berhenti adu_react`, dan `proses_reaksi_adu_react`.
   - Menggunakan state JSON dari database (`state_json`) untuk melacak count react.
2. **`bot/handlers/games.py`**:
   - Menambahkan routing untuk `adu_react` di fungsi-fungsi manajemen game utama.
   - Menambahkan `on_message_reaction` sebagai entry-point untuk update reaksi.
3. **`bot/handlers/register.py`**:
   - Mendaftarkan `MessageReactionHandler` dari `telegram.ext`.
4. **`main.py`**:
   - Menambahkan argumen eksplisit `allowed_updates=Update.ALL_TYPES` saat `run_polling()` untuk memastikan bot bisa menangkap notifikasi *Message Reaction*.

## Validasi
- `MessageReactionUpdated` secara delta (`len(new) - len(old)`) dihitung per id pesan yang masuk.
- Skor max react dihitung ketika command `/berhenti adu_react` dipanggil. 
- Terintegrasi penuh dengan ekosistem admin permission (`_is_admin()`) dan batasan grup.
