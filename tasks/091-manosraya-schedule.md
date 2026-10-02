# Task 091: Manosraya Schedule

## Latar Belakang
Fitur Manosraya (Yaksa Open Arms) yang berfungsi untuk menampung aspirasi anonim ternyata hanya dijadwalkan pada hari Senin sampai Jumat, pukul 10.00 hingga 22.00 WIB. Pengguna di luar jadwal tersebut sebelumnya masih dapat mengakses dan mengirim pesan anonim. Permintaan dari user adalah mencegah (menggagalkan) pengiriman jika dilakukan di luar jam operasional tersebut.

## Apa yang Dikerjakan
- Menambahkan validasi jadwal operasional di dalam fungsi `cmd_manosraya` di file `bot/handlers/manosraya.py`.
- Mengimpor `datetime` dan timezone `TZ` dari `bot.timefmt` agar pengecekan waktu sinkron dengan standar waktu bot (WIB).
- Menambahkan kondisi pengecekan:
  - Hari harus berkisar antara Senin hingga Jumat (`now.weekday() <= 4`).
  - Jam harus di antara 10.00 dan 21.59 (`10 <= now.hour < 22`).
- Jika user mengakses `/manosraya` di luar jadwal, bot akan membalas dengan informasi jam operasional dan langsung mengakhiri *conversation handler*.
- Memperbarui dokumentasi di `docs/commands.md` untuk merefleksikan jadwal fitur.

## Dampak Sistem
User yang mencoba mengetik `/manosraya` pada akhir pekan atau di luar jam 10.00-22.00 akan otomatis diblokir dari antarmuka aspirasi anonim. Tidak ada data log atau pesan yang diteruskan selama akses ini ditolak.
