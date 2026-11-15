# Task 149: Mengaktifkan Perintah /ijazah di Obrolan Grup

## Ringkasan Eksekutif
Menghapus pembatasan chat privat pada perintah `/ijazah` (`bot/handlers/graduation.py`) agar shishya maupun Admin dapat memamerkan atau mencetak Ijazah Kelulusan Resmi langsung di dalam grup Telegram, sama seperti perintah kartu identitas (`/kts`). Perintah `/transkrip` tetap dipertahankan khusus chat privat demi melindungi kerahasiaan nilai akademik shishya.

---

## Rincian Perubahan Teknis
- Menghapus pengecekan `_private_only_reply(update)` pada handler `cmd_ijazah`.
- Shishya dapat menggunakan `/ijazah` di grup untuk menampilkan ijazah miliknya sendiri.
- Admin tetap dapat mencetak ijazah mahasiswa lain di grup dengan menyertakan argumen NIM atau nama (`/ijazah <NIM/Nama>`), sementara non-admin tetap dicegah melihat ijazah shishya lain.
- Memperbarui dokumentasi perintah pada `docs/commands.md`.

---

## Verifikasi
- Pengujian eksekusi simulasi handler memverifikasi tidak ada error sintaksis.

