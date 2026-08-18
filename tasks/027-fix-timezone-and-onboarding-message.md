# 027 - Fix Timezone dan Pesan Onboarding

## Apa yang Dikerjakan
1. Mengubah format `datetime.datetime.now()` agar secara eksplisit menggunakan zona waktu **GMT+7** (Jakarta Time) pada `bot/handlers/common.py`.
2. Memodifikasi pesan balasan saat registrasi MABA pada `bot/handlers/messages.py` sehingga menyebutkan nama pengguna setelah mereka memasukkan nama.

## Mengapa Dikerjakan
1. **Timezone:** Penggunaan `datetime.datetime.now()` tanpa spesifikasi timezone seringkali menggunakan waktu server (yang mungkin saja UTC), sehingga jam yang muncul pada pesan, seperti _(Terakhir dicek: HH:MM:SS)_, menjadi kurang akurat dan membingungkan pengguna di Indonesia.
2. **Pesan Onboarding:** Mengubah pesan dari `"Terima kasih. Selanjutnya..."` menjadi `"Terima kasih, {nama}. Selanjutnya..."` membuat interaksi bot terasa lebih ramah dan personal.

## Bagaimana Alur Kodenya Bekerja
- Pada `bot/handlers/common.py`, di bagian pembentukan pesan verifikasi kembali, kita menginisialisasi object `timezone` dengan timedelta 7 jam. Hal ini menjamin bahwa setiap kali `now()` dipanggil dengan `tz`, waktunya sudah bergeser +7 jam dari UTC.
- Pada `bot/handlers/messages.py`, di _onboarding step_ `MABA_NAME`, variabel `name` yang sudah diformat ke Title Case langsung diinjeksikan ke dalam _f-string_ balasan sebelum bot meminta _step_ berikutnya yaitu `MABA_REASON`.
