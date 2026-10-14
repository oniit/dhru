# Task 102: Perbaikan Bug UnboundLocalError 'PENDAFTAR_CH_ID' pada Handler Callback

## Ringkasan Masalah
Pengguna/sistem mengalami error saat memproses callback pendaftaran Chāryārthī (`charyarthi:submit`):
```text
ERROR main Exception saat memproses update: cannot access local variable 'PENDAFTAR_CH_ID' where it is not associated with a value
Traceback (most recent call last):
  ...
  File "bot/handlers/commands.py", line 1217, in on_callback
    if PENDAFTAR_CH_ID:
UnboundLocalError: cannot access local variable 'PENDAFTAR_CH_ID' where it is not associated with a value
```

## Penyebab Akar Masalah (Root Cause)
Pada Python, jika suatu variabel di-assign atau di-import (`from ... import ...`) di mana pun dalam lingkup sebuah fungsi, nama variabel tersebut diperlakukan sebagai variabel lokal (_local variable_) untuk seluruh blok fungsi tersebut.

Pada fungsi `on_callback` di `bot/handlers/commands.py`:
1. Di cabang MABA (`elif action == "claim_ospek"`): terdapat impor lokal `from bot.settings import MABA_GROUP_LINK, PENDAFTAR_CH_ID`.
2. Di cabang Chāryārthī (`elif action == "submit"`): kode mencoba mengecek `if PENDAFTAR_CH_ID:`.
3. Karena alur eksekusi saat pengguna menekan tombol `charyarthi:submit` tidak melewati cabang `action == "claim_ospek"`, maka variabel lokal `PENDAFTAR_CH_ID` belum pernah diasosiasikan dengan nilai apa pun sebelum dibaca pada baris 1217, memicu `UnboundLocalError`.

Selain itu, terdapat beberapa impor lokal berulang lain di dalam `on_callback` dan fungsi lainnya (seperti `MABA_CH_IDS`, `MABA_GROUP_GIDS`, `MABA_GROUP_NAMES`, `KELOMPOK_GID`, dan `build_maba_verification_text`) yang berpotensi mengalami _scoping issue_ serupa jika diakses dari cabang kondisional lain.

## Solusi & Implementasi Teknis
1. **Promosi Impor ke Tingkat Modul (Module-Level Import)**:
   - Menambahkan konstanta `PENDAFTAR_CH_ID`, `MABA_GROUP_LINK`, `MABA_CH_IDS`, `MABA_GROUP_GIDS`, `MABA_GROUP_NAMES`, dan `KELOMPOK_GID` pada daftar impor `from bot.settings import (...)` di bagian atas file `bot/handlers/commands.py`.
   - Mengimpor `build_maba_verification_text` dari `.common` pada tingkat modul.
2. **Pembersihan Impor Lokal (Eliminate Nested Imports)**:
   - Menghapus impor lokal `PENDAFTAR_CH_ID` dan `MABA_GROUP_LINK` di dalam callback `maba:claim_ospek`.
   - Menghapus impor lokal `MABA_CH_IDS`, `MABA_GROUP_LINK`, dan `build_maba_verification_text` di callback `maba:verify`.
   - Menghapus impor lokal di dalam `cmd_lengkapi`, `cmd_daftar`, dan `setrole_maba_flow`.
3. **Penyempurnaan Penanganan Objek None**:
   - Memastikan pembacaan `first_name` dari `u_row` pada rekap pendaftaran Chāryārthī dan MABA aman terhadap `u_row` bernilai `None` atau `full_name` kosong.
4. **Verifikasi Mendalam (Dual-Registration QA)**:
   - Kompilasi modul dengan `python -m py_compile bot/handlers/commands.py` (berhasil tanpa error).
   - Menambahkan pengujian `test_both_registrations_forwarding_to_pendaftar_channel` pada `tests/test_charyarthi.py` yang memverifikasi kedua callback (`maba:claim_ospek` dan `charyarthi:submit`), perubahan role ke database, serta pengiriman pesan rekap ke channel `PENDAFTAR_CH_ID`.
   - Menjalankan seluruh pengujian `pytest tests/test_charyarthi.py` (4 passed, 100%).
