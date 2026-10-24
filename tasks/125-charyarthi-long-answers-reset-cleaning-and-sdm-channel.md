# Task 125: Perbaikan Komprehensif Alur Pendaftaran Chāryārthī & Migrasi SDM_CH_ID

## Ringkasan Perubahan
Menyelesaikan audit menyeluruh dan perbaikan bug sistem pendaftaran calon staf (**Chāryārthī**), mencakup kegagalan pratinjau dan pengiriman jawaban esai panjang, pembersihan data jawaban saat reset/batal/tolak, migrasi tujuan pengiriman ke channel tim SDM (`SDM_CH_ID`), serta pencegahan kebocoran kata kunci rahasia validasi LPM.

---

## Masalah & Akar Penyebab (Root Cause)

1. **Jawaban Panjang Gagal Dipreview & Gagal Diteruskan**:
   - **Pratinjau Jawaban (`charyarthi:preview`)**: Bot sebelumnya menggabungkan seluruh teks pertanyaan dan jawaban pelamar ke dalam satu string `prev_text` tanpa paginasi. Ketika total karakter melebihi 4.096 karakter, Telegram menolak permintaan dengan error `BadRequest: Message is too long`. Begitu pula pada menu pengisian soal (`charyarthi:ans_q`), jika jawaban sebelumnya sangat panjang, preview `msg_text` melebihi limit.
   - **Penerusan ke SDM**: Pengelompokan blok jawaban sebelumnya hanya mengecek `len(cur_block) + len(entry) > 3800`. Jika ada satu jawaban esai pelamar yang berukuran > 3.500 karakter, satu entri tersebut langsung melampaui 4.096 karakter dan memicu error `Message is too long`. Karena penanganan exception berada di luar per-blok, kegagalan 1 blok menghentikan pengiriman sisa jawaban lainnya.
   - **Penerusan ke Channel Pendaftar (`PENDAFTAR_CH_ID`)**: Teks `charyarthi_reason` (alasan mendaftar) disematkan utuh pada kartu ringkasan. Jika pelamar mengetik alasan yang panjang, kartu pendaftar gagal terkirim.

2. **Jawaban Tetap Ada Saat User Direset**:
   - `Database.reset_user_all_data`, `reset_all_users_all_data_except_env`, dan `reset_all_data_except_users` sebelumnya tidak menjalankan kueri `DELETE FROM charyarthi_answers`.
   - Tombol pembatalan (`charyarthi:cancel`) dan penolakan admin (`charyarthi:rej` / `/reject_charyarthi`) hanya mengubah status tanpa membersihkan tabel `charyarthi_answers` dan field target divisi di `profile_json`.

3. **Kebocoran Kata Kunci Validasi LPM ke User**:
   - Pada `bot/handlers/promo.py` dan `checker.py`, pesan kegagalan secara eksplisit menampilkan teks rahasia: `Wajib memuat kata kunci: <b>{lpm_keyword}</b>`. Hal ini membocorkan syarat internal ke pengguna.

4. **Migrasi Konfigurasi `SDM_GID` ke `SDM_CH_ID`**:
   - Konfigurasi tim SDM beralih dari grup ke channel Telegram (`SDM_CH_ID`). Kode sebelumnya hanya mengimpor dan mengecek `SDM_GID`.

---

## Solusi & Implementasi Teknis

### 1. Paginasi Pratinjau Jawaban & Anti-Limit Teks
- Menambahkan fungsi pembantu `render_charyarthi_quiz_preview_page(uid, div_id, page_idx, conn, db)` di `bot/handlers/common.py`:
  - Menampilkan soal dan jawaban per nomor dengan navigasi `[◀️ Soal Sebelumnya]`, `[📌 X/Total]`, `[Soal Berikutnya ▶️]`, `[✏️ Ubah Jawaban]`, dan `[🚀 Lanjut ke Berkas]`.
  - Membatasi teks jawaban pratinjau maksimal 2.800 karakter dengan catatan informatif jika jawaban melebihi batas.
- Pada `action == "preview"` di `bot/handlers/commands.py`:
  - Jika total gabungan seluruh jawaban $\le$ 3.500 karakter, tampilkan ringkasan semua soal sekaligus.
  - Jika total gabungan > 3.500 karakter, sistem otomatis mengalihkan tampilan ke mode halaman per soal (`charyarthi:prev_q`) halaman 0, mencegah error `Message is too long`.
- Pada `action == "ans_q"`, pratinjau jawaban eksisting dipangkas aman ($\le$ 2.000 karakter) sebelum ditampilkan dalam blockquote.

### 2. Chunking Jawaban & Pengiriman Aman ke `SDM_CH_ID` dan `PENDAFTAR_CH_ID`
- **SDM Channel Streaming**:
  - Jawaban esai pelamar yang panjang dipecah secara rekursif menjadi sub-bagian $\le$ 2.400 karakter berdasarkan baris baru/potongan teks.
  - Setiap sub-bagian dikemas rapi (`entry` $\le$ 2.800 karakter) dan digabung ke dalam blok pesan bertahap $\le$ 3.400 karakter.
  - Setiap blok dikirim dalam blok `try...except` mandiri dengan fallback pengiriman biasa tanpa reply jika channel tidak mendukung reply thread, sehingga kegagalan satu blok tidak membatalkan blok lainnya.
- **Kartu Pendaftar (`PENDAFTAR_CH_ID`)**:
  - Menampilkan cuplikan alasan mendaftar maksimal 600 karakter pada kartu header utama.
  - Jika alasan mendaftar > 600 karakter, bot otomatis mengirim pesan lanjutan sebagai balasan (*reply*) yang memuat seluruh alasan mendaftar secara lengkap.

### 3. Pembersihan Bersih Jawaban Saat Reset, Batal, dan Tolak
- Memperbarui `bot/database.py`:
  - `reset_user_all_data`: mengeksekusi `DELETE FROM charyarthi_answers WHERE telegram_id = ?`.
  - `reset_all_users_all_data_except_env`: mengeksekusi `DELETE FROM charyarthi_answers WHERE telegram_id IN (...)`.
  - `reset_all_data_except_users`: mengeksekusi `DELETE FROM charyarthi_answers`.
- Memperbarui `commands.py`:
  - `charyarthi:cancel`: menghapus jawaban pelamar dan mereset field `target_division_1`, `target_division_2`, `charyarthi_reason`, `application_status`.
  - `charyarthi:rej` & `/reject_charyarthi`: mereset seluruh field pendaftaran calon staf dan menghapus jawaban esai pelamar dari database.
  - Dashboard kuis (`render_charyarthi_quiz_view`): menyediakan tombol `[🗑 Reset Jawaban Saya]` dengan konfirmasi dialog (`charyarthi:reset_confirm` dan `charyarthi:do_reset`) agar pengguna dapat mengulang pengisian tes dari awal jika diinginkan.

### 4. Perlindungan Kerahasiaan Kata Kunci LPM
- Pada `bot/handlers/promo.py` dan `checker.py`, pesan kesalahan kegagalan validasi kata kunci diubah menjadi pesan umum yang ramah pengguna:
  `Pesan di tautan tidak memuat teks/materi promosi resmi yang valid. Pastikan Anda menyebarkan postingan promosi yang benar.`
- Kata kunci rahasia internal bot tidak lagi bocor ke pengguna akhir.

### 5. Dukungan Konfigurasi `SDM_CH_ID`
- Pada `bot/settings.py`:
  ```python
  _sdm_ch = os.environ.get("SDM_CH_ID", "").strip()
  _sdm_gid = os.environ.get("SDM_GID", "").strip()
  SDM_CH_ID = int(_sdm_ch) if _sdm_ch else (int(_sdm_gid) if _sdm_gid else None)
  SDM_GID = SDM_CH_ID
  ```
- Menyesuaikan fungsi otorisasi `_can_manage_soal` dan pengecekan callback `soal:` di `commands.py` untuk mengizinkan interaksi dari `SDM_CH_ID`.

### 6. Pencegahan Double-Submit & Validasi Divisi
- Menambahkan validasi `target_division_1` sebelum pemrosesan submit pendaftaran.
- Menambahkan *idempotency guard*: jika pelamar sudah berstatus `ROLE_CHARYARTHI` atau pengajuan berstatus `PENDING`/`ACCEPTED`, klik tombol berulang kali tidak akan menduplikasi kartu ke channel admin maupun channel SDM.

---

## Verifikasi & Pengujian
- **Pengujian Unit & Integrasi (`tests/test_charyarthi.py`)**:
  - `test_charyarthi_long_answers_preview_and_forwarding`: memverifikasi jawaban esai panjang (> 3.000 karakter) dan alasan panjang (> 1.600 karakter) aman dari batas 4.096 karakter Telegram, berhasil dialihkan ke mode paginated preview, terkirim bertahap ke `SDM_CH_ID`, serta terhapus bersih saat user di-reset.
  - `test_promo_keyword_not_leaked`: memverifikasi kata kunci rahasia LPM tidak pernah muncul dalam pesan error ke pengguna.
  - Seluruh rangkaian pengujian pada `tests/test_charyarthi.py` (9/9 pengujian) berhasil lulus (*passed*).
