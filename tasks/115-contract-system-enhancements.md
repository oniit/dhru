# 115 Contract System Enhancements & State Machine

## Ringkasan Perubahan
Memperbarui sistem manajemen kontrak kerja internal (`bot/handlers/kontrak.py`) dengan mengimplementasikan:
1. **Otomatisasi Rollover Periode Berikutnya pada H-7**: Mengatasi masalah pengesahan kontrak staf di akhir periode yang sebelumnya hanya berumur beberapa hari.
2. **Validasi Isolasi Perubahan TTD Staf Lama**: Memisahkan aksi upload tanda tangan dari eksekusi penerbitan kontrak, mencegah reset masa kontrak dan spam notifikasi ke Owner.
3. **Alur Draf & Pengesahan Eksplisit Staf Baru**: Menampilkan draf kontrak terlebih dahulu dengan tombol inline interaktif `[✍️ Sahkan & Terbitkan Kontrak]` dan perintah `/kontrak sahkan`.
4. **Pencatatan Riwayat Teks (History) & ID Staf Tetap**: Menjaga nomor urut staf (`contract_seq_no`) tetap sebagai ID permanen, mencatat tanggal bergabung (`internal_since`), jumlah termin (`contract_count`), dan daftar riwayat teks perpanjangan (`contract_history`) tanpa menyimpan file gambar usang.
5. **Guard & Perbaikan `/kontrak renew`**: Mencegah perpanjangan dini jika kontrak masih aktif dengan sisa waktu > 7 hari.

---

## Latar Belakang & Masalah
- **Masalah 1 (Periode Terpotong H-7)**: Masa akhir kontrak Dhruva jatuh pada tanggal 17 setiap bulan genap. Pada implementasi lama, jika staf baru mendaftar atau staf lama renew di H-7 (tanggal 10-16 bulan genap), masa berakhirnya tetap diset tanggal 17 bulan yang sama. Akibatnya kontrak langsung kadaluarsa dalam 1–7 hari.
- **Masalah 2 (Ganti TTD Dianggap Kontrak Baru)**: Saat staf lama yang kontraknya sedang aktif mengunggah TTD baru via `/kontrak ttd` lalu membuka `/kontrak saya`, sistem lama langsung memanggil `calculate_contract_period(time.time())` dan menimpa tanggal mulai/akhir serta mengirim notifikasi ke Owner bahwa staf tersebut baru mengisi kontrak kerja.
- **Masalah 3 (Hilangnya Rekam Jejak / History)**: Nomor urut surat selalu menimpa tanggal lama di `profile_json`. Admin tidak bisa mengetahui sejak kapan seorang staf bergabung dan sudah berapa kali memperbarui kontrak.

---

## Solusi & Detail Teknis

### 1. `calculate_contract_period(start_timestamp, is_new_or_renew=True)`
- Menambahkan parameter `is_new_or_renew`.
- Pada penandatanganan baru atau renew (`is_new_or_renew=True`), jika jatuh pada bulan genap dengan tanggal $\ge$ 10 (ambang batas H-7 sebelum penutupan tanggal 17), periode akhir otomatis dilompati ke tanggal **17 bulan genap berikutnya (+2 bulan)**.
- Menangani rollover tahun dengan aman jika bulan berikutnya melebihi Desember ($> 12 \rightarrow$ Februari tahun berikutnya).
- Untuk pengecekan kalender organisasi (`is_new_or_renew=False`), tanggal akhir tetap mengacu pada tanggal 17 terdekat hingga periode tersebut benar-benar ditutup.

### 2. State Machine Evaluasi Status Kontrak (`_get_contract_status`)
Mengklasifikasikan kondisi kontrak pengguna secara akurat berdasarkan `contract_end_ts` dan `contract_seq_no`:
- `has_contract: False` $\rightarrow$ Staf baru yang belum mengesahkan kontrak.
- `is_active: True` $\rightarrow$ Kontrak sedang aktif berjalan dan belum masuk jendela H-7 ($> 7$ hari tersisa).
- `is_expiring: True` $\rightarrow$ Masa berlaku tersisa $< 7$ hari (H-7, status ikon `⚠️`).
- `is_expired: True` $\rightarrow$ Waktu saat ini telah melewati masa akhir (status ikon `❌`).

### 3. Pembaruan Handler `on_kontrak_ttd`
- Menyimpan `file_id` ke `ttd_file_id`.
- Jika status staf `is_active`: Mengirim respons ramah bahwa TTD berhasil diperbarui untuk periode yang sedang berjalan tanpa mengubah tanggal maupun mengirim notifikasi baru ke Owner.
- Jika `is_expiring` atau `is_expired`: Mengarahkan staf untuk menjalankan `/kontrak renew`.
- Jika staf baru: Mengarahkan staf untuk membuka `/kontrak saya` guna meninjau draf.

### 4. Alur `/kontrak saya`, Draf, dan Pengesahan
- Jika `is_active`: Menampilkan gambar kontrak aktif yang sudah ada beserta nomor surat resmi tanpa menulis ulang database.
- Jika `is_expiring` atau `is_expired`: Menampilkan pemberitahuan masa berakhir dengan tombol inline perpanjangan.
- Jika staf baru:
  - Jika belum ada TTD: Memberikan instruksi `/kontrak ttd`.
  - Jika sudah ada TTD: Menghasilkan gambar draf kontrak (`DRAFT/DK.A/...`) dengan tombol `[✍️ Sahkan & Terbitkan Kontrak]` dan panduan perintah `/kontrak sahkan`.
- Saat disahkan (`_execute_sahkan_kontrak`):
  - Mengambil nomor urut atomic `get_next_contract_seq`.
  - Menetapkan `internal_since = start_str`, `contract_count = 1`, `contract_seq_no = seq`.
  - Menginisialisasi `contract_history` (array berisi tanggal, nomor surat, dan iterasi).
  - Mengirim notifikasi gambar resmi ke staf dan pemberitahuan ke `OWNER_ID`.

### 5. Penyempurnaan `/kontrak renew`
- Dibatasi hanya jika staf telah memiliki kontrak dan statusnya `is_expiring` (H-7) atau `is_expired`.
- Percobaan renew sebelum H-7 diblokir dengan pemberitahuan sisa hari aktif.
- Nomor urut `seq` staf dipertahankan tetap.
- Counter `contract_count` bertambah $+1$.
- Entri baru ditambahkan ke dalam `contract_history`.
- Tanggal baru diperbarui ke periode genap berikutnya (+2 bulan).

### 6. Admin Tools (`/kontrak check` & `/kontrak all`)
- `/kontrak check <target>`: Mengirimkan gambar kontrak staf serta teks rincian lengkap: ID Staf, status keaktifan, tanggal bergabung sejak kapan, jumlah perpanjangan, dan daftar riwayat teks seluruh penandatanganan kontrak sebelumnya.
- `/kontrak all`: Menampilkan status ikon (`✅`, `⚠️`, `🔄`, `❌`), nomor ID `[ID: xxxx]`, iterasi `• Ke-N`, dan tanggal bergabung `• Sejak <tanggal>`.

---

## Verifikasi & Pengujian
- Unit test otomatis ditambahkan pada `tests/test_kontrak_enhancements.py` mencakup:
  1. Perhitungan periode H-7 bulan genap, ganjil, dan rollover akhir tahun Desember $\rightarrow$ Februari.
  2. Evaluasi status kontrak (`active`, `expiring`, `expired`, `empty`).
- Integration test end-to-end ditambahkan pada `tests/test_kontrak_e2e_qa.py` mencakup:
  1. Role gate security (penolakan user publik/mahasiswa).
  2. Alur staf baru (upload TTD, draf preview, dan pengesahan resmi nomor urut).
  3. Pembaruan TTD staf lama tanpa mereset masa berlaku kontrak.
  4. Blokir perpanjangan dini jika $> 7$ hari dan eksekusi sukses saat H-7.
  5. Pengujian admin tools (`/kontrak all` dan `/kontrak check`).
- Menjalankan test suite proyek `tests/test_runner.py` dan `tests/` secara penuh: seluruh 36 test suites dinyatakan **100% PASS**.
