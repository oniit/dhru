# Task 153: Dedicated /help_owner Command and Graduation ZIP JSON Inclusion

## Latar Belakang & Masalah
1. **Penyelarasan Tampilan `/help` untuk Owner & Pembuatan `/help_owner`**:
   Sebelumnya, saat Owner mengetik perintah `/help`, tampilan pesan dipenuhi oleh blok teks perintah khusus Owner yang panjang, membuat navigasi perintah standar menjadi kurang rapi. Selain itu, Owner membutuhkan panduan terdedikasi yang merangkum seluruh wewenang, kontrol sistem, dan perintah khusus Founder/Owner agar tidak terlupakan, sementara `/help` biasa cukup menampilkan menu yang bersih dan seragam seperti tampilan Admin.
2. **Keterlacakan Data pada Paket ZIP Ekspor Kelulusan (`/export_kelulusan zip`)**:
   Sebelumnya, paket ZIP hanya berisi file gambar Transkrip dan Ijazah (`.png`). Pengelola menghendaki agar berkas data JSON angkatan terkait disertakan langsung di dalam paket ZIP dan di folder output (`output/kelulusan_gen{N}/`), sehingga siapa pun yang mengekstrak berkas dapat langsung mengetahui dan memvalidasi sumber data resmi yang digunakan untuk merender transkrip dan ijazah angkatan tersebut.

## Solusi & Implementasi Teknis
1. **Penyelarasan Tampilan `/help` & Handler `/help_owner`**:
   - Di `bot/handlers/commands.py`, blok perintah Owner dihapus dari fungsi perender umum `help_for_role`.
   - Pada handler `cmd_help`, jika pengguna yang memanggil adalah Owner (`is_owner(uid)` atau `role == ROLE_OWNER`), sistem otomatis meminjam format tampilan `ROLE_ADMIN` yang bersih, lalu menambahkan catatan kaki:
     `💡 Khusus Founder/Owner: Ketik /help_owner untuk melihat seluruh perintah wewenang Owner.`
   - Mengimplementasikan handler baru `cmd_help_owner` (dan alias `/ownerhelp`):
     - Membatasi akses ketat hanya untuk akun Founder/Owner (`is_owner(update.effective_user.id)`).
     - Menyajikan ensiklopedia terstruktur berisi seluruh perintah administratif tingkat Owner: Penutupan Generasi (`/setrole purna all`, `/tutup_generasi`), Manajemen Akun & Migrasi (`/pindah_data`, `/admin_data`, `/chat`), Kode Akses & Promosi (`/gencode`, `/promo`, `/ospek_mode`), Penyiaran (`/broadcast`, `/trigger`), Kelulusan & Transkrip (`/export_kelulusan`, `/sync_kelulusan`), Reset Sistem (`/owner_reset`, `/orreset_user`, `/orreset_agra`), dan Pemeliharaan Server (`/reload`, `/pull`).
   - Mendaftarkan handler `help_owner` dan `ownerhelp` pada `bot/handlers/register.py`.
2. **Penyertaan File JSON pada Ekspor Kelulusan & Paket ZIP**:
   - Di `bot/handlers/graduation.py` fungsi `_sync_export_documents`, sistem otomatis menulis berkas arsip data JSON spesifik angkatan (`graduation_records_gen{gen_val}.json`) langsung ke dalam folder keluaran `output/kelulusan_gen{gen_val}/`.
   - Berkas JSON tersebut dimasukkan ke dalam daftar `created_files`.
   - Pada saat pembuatan paket ZIP (`_make_zip`), berkas JSON angkatan (`graduation_records_gen{gen_val}.json`) dan master JSON (`graduation_records_master.json`) otomatis dipaketkan ke dalam root file `.zip`.
   - Caption dan notifikasi pesan diperbarui untuk mengonfirmasi penyertaan berkas data JSON di dalam paket ZIP.

## Berkas yang Diperbarui & Ditambahkan
- `bot/handlers/commands.py`: Penyelarasan `cmd_help` untuk Owner dan penambahan `cmd_help_owner`.
- `bot/handlers/register.py`: Registrasi perintah `help_owner` dan `ownerhelp`.
- `bot/handlers/graduation.py`: Penyertaan data JSON pada `_sync_export_documents` dan packaging ZIP.
- `docs/commands.md` & `docs/architecture.md`: Dokumentasi perintah `/help_owner` dan pembaruan spesifikasi packaging ekspor ZIP.
- `tests/test_help_and_export_json.py`: Test suite pengujian otomatis untuk memverifikasi tampilan `/help`, proteksi `/help_owner`, dan integritas berkas JSON di dalam ZIP (2/2 Suites PASS).

## Hasil Pengujian
- `tests/test_help_and_export_json.py`: **2/2 Suites PASSED** (0.42s).
- `tests/test_mass_setrole_purna.py`: **6/6 Suites PASSED** (0.61s).
- `tests/test_qa_master_audit.py`: **67/67 Tests PASSED** (0.83s).
- Seluruh dokumen kelulusan, proteksi keamanan, dan alur bot berjalan 100% stabil tanpa regresi.
