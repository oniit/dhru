# Task 107: Sistem Kuesioner Tes Khusus Divisi Chāryārthī & Pengaturan Soal SDM

## Latar Belakang & Masalah
Pada seleksi calon staf (Chāryārthī), formulir berkas umum menggunakan tautan Google Form. Namun, untuk menilai kompetensi spesifik pelamar per divisi, dibutuhkan rangkaian pertanyaan tambahan (studi kasus/esai sekitar 3–8 pertanyaan) yang fleksibel dan dapat dikelola langsung oleh admin/staf SDM (`SDM_GID`) tanpa kerumitan koding.

Kekhawatiran utama yang dipecahkan dalam perancangan ini meliputi:
1. **Tekanan Psikologis & UI/UX Pelamar**: Menjawab esai panjang lewat chat linier kaku (1-per-1) membuat pelamar tertekan, cemas jika salah ketik atau terkirim sebelum selesai.
2. **Limit Teks Telegram**: Pesan Telegram dibatasi maksimal 4.096 karakter. Jika jawaban esai banyak dan digabungkan menjadi 1 pesan, pesan akan gagal terkirim (*Message is too long*).
3. **Kemudahan Admin SDM Awam**: Admin SDM membutuhkan cara input soal yang semudah mungkin tanpa harus mengerti perintah bot rumit atau sintaks database.

## Solusi & Arsitektur Teknis

### 1. Database Schema (`bot/database.py`)
Menambahkan dua tabel baru dengan migrasi otomatis ke remote database Turso:
- `charyarthi_questions`:
  - `id`: Primary Key Auto Increment.
  - `division_id`: Divisi target (misal: `d_editor`, `d_hrd`).
  - `question_order`: Urutan nomor pertanyaan (1, 2, 3...).
  - `question_text`: Teks soal tes.
  - `created_at`: Waktu pembuatan.
- `charyarthi_answers`:
  - `id`: Primary Key Auto Increment.
  - `telegram_id`: ID Telegram pelamar.
  - `division_id`: Divisi target.
  - `question_id`: Foreign key ke pertanyaan.
  - `answer_text`: Jawaban esai pelamar.
  - `updated_at`: Waktu penyimpanan jawaban terakhir.
  - Constraint `UNIQUE (telegram_id, division_id, question_id)`.

Menyediakan metode CRUD lengkap pada kelas `Database`:
- `get_charyarthi_questions(conn, division_id)`
- `get_charyarthi_question_by_id(conn, question_id)`
- `set_charyarthi_questions_bulk(conn, division_id, questions)`
- `add_charyarthi_question(conn, division_id, question_text)`
- `delete_charyarthi_question(conn, question_id)`
- `clear_charyarthi_questions(conn, division_id)`
- `get_charyarthi_answers(conn, telegram_id, division_id)`
- `save_charyarthi_answer(conn, telegram_id, division_id, question_id, answer_text)`
- `clear_charyarthi_user_answers(conn, telegram_id)`

### 2. UI/UX Pelamar Berbasis Dashboard Soal Interaktif (`render_charyarthi_quiz_view`)
Alih-alih chat beruntun yang menekan, pelamar diberikan tampilan kartu navigasi (Dashboard Soal):
- **Bebas Urutan**: Pelamar dapat memilih nomor mana yang ingin dijawab terlebih dahulu.
- **Draft Otomatis & Bebas Edit**: Jawaban tersimpan di database dan dapat diedit berulang kali sebelum pendaftaran di-submit.
- **Pratinjau (Preview)**: Tombol `[ 👁 Pratinjau Semua Jawaban ]` menampilkan seluruh rekap jawaban sebelum dikirim.
- **Tombol Lanjut Dinamis**: Tombol submit berkas hanya aktif jika seluruh soal tes divisi telah terisi. Jika divisi tidak memiliki soal tes tambahan, sistem langsung melompat ke formulir umum tanpa hambatan.
- **Limit Teks Aman**: Pelamar menjawab 1 pesan per soal, memberikan kuota hingga 4.096 karakter untuk tiap jawaban esai.

### 3. Pengiriman Berkas Lengkap ke `SDM_GID` & Anti-Limit 4.096 Karakter
Saat pelamar menekan submit:
- Notifikasi rekap umum tetap masuk ke channel pendaftar (`PENDAFTAR_CH_ID`).
- Notifikasi khusus diteruskan ke grup tim SDM (`SDM_GID`).
- Jika terdapat jawaban tes divisi, bot otomatis memformat lembar jawaban secara terstruktur dengan fitur *chunk splitting* (maksimal ~3.800 karakter per pesan) dan mengirimkannya sebagai pesan balasan (*reply*) bersambung ke header pelamar di `SDM_GID`, mencegah terjadinya error `Message is too long`.

### 4. Manajemen Soal Ramah Awam untuk Admin SDM
Menyediakan perintah dan menu inline keyboard:
- `/soal [divisi]` atau `/soal_divisi`: Menampilkan antarmuka tombol inline pemilihan divisi, melihat daftar soal, menambah 1 soal, menghapus soal, atau mengosongkan soal.
- `/setsoal <divisi>\n1. Soal 1\n2. Soal 2...`: Bulk paste cepat. Admin cukup copy-paste daftar soal bernomor dari catatan atau WhatsApp.
- `/tambah_soal <divisi> <pertanyaan>`: Menambah 1 soal di urutan terakhir.
- `/hapus_soal <divisi> <no>`: Menghapus 1 soal nomor tertentu dan mengurutkan ulang sisa soal.
- `/reset_soal <divisi>`: Mengosongkan seluruh soal divisi tertentu.
- Helper `resolve_division_id`: Memungkinkan admin mengetik nama ringkas (contoh: `editor`, `sdm`, `eksternal`, `sarpras`) tanpa harus menghafal ID teknis (`d_editor`, `d_hrd`, dsb).

## Verifikasi & QA
- Ditambahkan unit test komprehensif pada `tests/test_charyarthi.py` (`test_charyarthi_division_questions_and_answers`):
  - Pengujian `resolve_division_id` untuk berbagai variasi nama divisi.
  - Pengujian bulk insert, penambahan soal, dan penghapusan soal (re-indexing urutan nomor 1..N).
  - Pengujian penyimpanan dan penarikan jawaban pelamar.
  - Pengujian rendering dashboard progres pengisian (1/3 soal -> tombol not_ready; 3/3 soal -> tombol ready).
  - Pengujian integrasi pengiriman notifikasi submit ke `PENDAFTAR_CH_ID` dan `SDM_GID`.
- Seluruh rangkaian pengujian `pytest tests/test_charyarthi.py` lulus 100% (6 passed).
