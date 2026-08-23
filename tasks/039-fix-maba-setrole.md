# Fix Bypass Set Role Maba Crash & Announcement

## Ringkasan
Memperbaiki _bug_ di mana saat admin/owner melakukan `/setrole <id> maba`, tidak ada balasan konfirmasi, maba tidak mendapat notifikasi, dan tidak ada pengumuman masuk ke channel `KELOMPOK_GID`.

## Penyebab Bug
Pada blok fungsi untuk _bypass role_ `maba` di `bot/handlers/commands.py`, sistem mencoba melakukan import `MABA_GROUP_LINKS` dari `bot.settings`. Sayangnya, variabel tersebut tidak ada (terjadi `ImportError`), sehingga eksekusi program terhenti di tengah jalan sebelum pesan konfirmasi dan pesan notifikasi ke *user* dieksekusi.

## Solusi yang Diterapkan
1. **Perbaikan Generator Tautan (Link)**: Alih-alih melakukan impor dari konstanta yang tidak ada, bot kini mem-generate ulang _invite link_ (satu kali pakai/limit 1) secara dinamis menggunakan `MABA_GROUP_GIDS` seperti alur verifikasi Maba normal.
2. **Notifikasi ke Grup Kelompok (KELOMPOK_GID)**: Menambahkan blok program yang mengirimkan notifikasi "*Alokasi Kelompok MABA (Jalur Admin)*" ke `KELOMPOK_GID` ketika admin mengubah role seseorang menjadi Maba secara _bypass_.
3. Memperbaiki impor yang salah, sehingga admin/owner bisa kembali mendapatkan balasan "Set role selesai" saat command dijalankan.
