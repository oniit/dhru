# 050 - Kantong Rempah Counter (Reminders)

## Deskripsi
Menambahkan fitur *counter* / pengingat waktu (1 menit, 30 detik, dan 15 detik) untuk game **Kantong Rempah**, seperti yang sebelumnya dibuat pada game Tujuh Pusaka. Pengingat ini berlaku pada dua fase yang ada dalam game:
1. Fase Setor Rempah
2. Fase Tebak Rempah

## Perubahan Kode
- Memodifikasi fungsi `mulai_kantong_rempah` di `bot/games/kantong_rempah.py` untuk menjadwalkan task `job_queue` pengingat sebelum batas waktu fase setor berakhir.
- Memodifikasi fungsi `job_end_deposit_phase` untuk menjadwalkan task `job_queue` pengingat sebelum batas waktu fase tebak berakhir.
- Menambahkan fungsi baru `job_kantong_rempah_reminder` yang bertugas menampilkan pesan ke grup. Fungsi ini mengecek properti `phase` saat ini di database dengan `expected_phase` dari *job* (agar pengingat fase setor tidak terkirim jika admin mempercepat *skip* ke fase tebak atau game dihentikan).
- Sistem ini dinamis, jika batas waktu (`menit_setor` atau `menit_tebak`) diatur <= 1 menit, maka pengingat "1 menit lagi" tidak akan dibuat (hanya 30 dan 15 detik) untuk mencegah spam di detik pertama game mulai.
