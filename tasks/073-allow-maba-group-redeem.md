# Allow Maba to Redeem Group Code

## Deskripsi
Fitur ini mengubah perilaku bot saat memvalidasi input kode akses. Sebelumnya, jika pengguna yang sudah memiliki *role* `maba` memasukkan kode akses yang juga bertarget `maba`, bot akan otomatis menolak dan membatalkan aksinya.

Dengan pembaruan ini, jika pengguna dengan role `maba` memasukkan kode `maba` tetapi **belum memiliki grup kelompok** (`maba_group` belum diset di dalam profilnya), bot akan mengizinkannya untuk menggunakan kode tersebut sehingga sistem bisa memproses pembagian grup untuknya.

## Detail Implementasi
- Di `bot/handlers/messages.py` pada step `INPUT_CODE`:
  - Mengambil data profil JSON dari `row` pengguna.
  - Jika role awal dan target sama-sama `maba`, ditambahkan pengecekan: `if target_role == "maba" and "maba_group" not in prof:`.
  - Jika belum memiliki `maba_group`, sistem mengizinkan proses berlanjut (`pass`) untuk mengonsumsi kode.
  - Jika sebaliknya, sistem tetap menolak seperti sebelumnya dengan peringatan gagal.
