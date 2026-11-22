# Task 166: Penamaan Resmi Warkat (Prakarsha & Svatantra), Input 3 Alasan Divisi, dan Audit Perhitungan Generasi

## Ringkasan Tugas
Menyesuaikan terminologi dan fungsionalitas Warkat Kehormatan serta mengaudit logika perhitungan masa berlaku generasi:
1. **Pembaruan Nomenklatur Jalur Warkat**:
   - Jalur Staf resmi dinamakan **Jalur Prakarsha** (sebelumnya Jalur Khusus Charya).
   - Jalur Tanpa Ospek resmi dinamakan **Jalur Svatantra** (Bebas Pravesa / Tanpa Ospek).
2. **Input 3 Alasan Pemilihan Divisi (Jalur Prakarsha)**:
   - Setelah memilih 3 divisi (`d1`, `d2`, `d3`), bot meminta pengguna menginputkan **3 alasan terpisah** untuk masing-masing divisi yang dipilih via private message (`WARKAT_REASON_1`, `WARKAT_REASON_2`, `WARKAT_REASON_3`).
   - Alasan disimpan dalam `context.user_data["warkat_flow"]` dan dimasukkan ke `profile_json` (`reason_division_1`, `reason_division_2`, `reason_division_3`, dan `charyarthi_reason`).
   - Tampilan konfirmasi akhir dan notifikasi ke Channel SDM (`SDM_CH_ID`) menampilkan 3 alasan tersebut di bawah masing-masing divisi pilihan sebagai bahan pertimbangan Tim SDM dalam menentukan penempatan divisi yang paling tepat.
3. **Audit Perhitungan Generasi (Gen 1 vs Gen 4) & Penyesuaian Rumus (`current_gen + 1`)**:
   - Warkat Kehormatan dirilis untuk alumni berprestasi/kehormatan setelah suatu generasi ditutup (`/generasi_tutup`).
   - Pada saat generasi ditutup, sistem otomatis menaikkan `current_generasi` ke generasi berikutnya (misal Gen 1 selesai -> menjadi Gen 2).
   - Hak istimewa Jalur Svatantra berlaku selama **2 generasi**: yaitu generasi yang baru dibuka (Gen 2) dan 1 generasi setelahnya (Gen 3).
   - Maka rumus batas generasi disesuaikan menjadi:
     `max_gen = current_gen + 1`
     Dengan rumus ini, saat warkat dibuat di Gen 2: `max_gen = 2 + 1 = 3` (berlaku di Gen 2 dan Gen 3).
     Sebelumnya digunakan `current_gen + 2` yang menyebabkan `2 + 2 = 4` (mencakup 3 generasi).
   - Kode di `bot/handlers/commands.py` telah diperbarui ke `current_gen + 1`.

## Perubahan Teknis
- **`bot/handlers/commands.py`**:
  - `cmd_gencode_warkat`: Label masa berlaku diperbarui menjadi Prakarsha (Staf) dan Svatantra (Pravesa).
  - `cmd_gencode_warkat_avail`: Tabel daftar warkat belum dipakai diperbarui menggunakan istilah Prakarsha dan Svatantra.
  - `handle_warkat_callback`:
    - Callback `warkat:cdiv3`: Setelah divisi ke-3 dipilih, bot mengarahkan pengguna untuk menginputkan alasan divisi 1 (`WARKAT_REASON_1:{code}`).
    - Callback `warkat:csubmit`: Membaca `r1`, `r2`, `r3` dari flow, menyimpannya ke profil, dan menyusun pesan `msg_admin` lengkap dengan alasan per divisi untuk evaluasi SDM.
- **`bot/handlers/messages.py`**:
  - `handle_input_code`: Tampilan keyboard penukaran kode menggunakan label Prakarsha dan Svatantra.
  - `on_private_message`:
    - Menangani input step `WARKAT_REASON_1:{code}` -> menyimpan `r1` dan meminta alasan divisi 2 (`WARKAT_REASON_2:{code}`).
    - Menangani input step `WARKAT_REASON_2:{code}` -> menyimpan `r2` dan meminta alasan divisi 3 (`WARKAT_REASON_3:{code}`).
    - Menangani input step `WARKAT_REASON_3:{code}` -> menyimpan `r3`, membersihkan step, dan menampilkan ringkasan konfirmasi pendaftaran Jalur Prakarsha beserta tombol submit.
- **`docs/architecture.md` & `docs/commands.md`**:
  - Diperbarui dengan deskripsi alur Jalur Prakarsha (3 divisi + 3 alasan) dan Jalur Svatantra.
- **`tests/test_warkat.py` & `tests/test_qa_master_audit.py`**:
  - Ditambahkan unit test dan integrasi untuk skenario pengisian 3 alasan secara sekuensial.
  - Seluruh 93 tes QA master audit dan 20 tes pytest lulus 100%.
