# Task 093: Resolusi Menyeluruh Bug & Celah Sistem Hasil Deep Production QA Audit

## Ringkasan Eksekutif
Berdasarkan hasil temuan pada Task 092 (`092-deep-production-qa-audit.md`), dilakukan perbaikan menyeluruh terhadap 8 celah keamanan, bug konkurensi, kebocoran state finansial, dan kesenjangan spesifikasi perintah di seluruh subsistem bot. Seluruh perbaikan telah divalidasi dengan rangkaian uji regresi otomatis (`tests/test_deep_qa.py`) dan rangkaian pengujian penuh (`pytest`) dengan tingkat keberhasilan 100%.

---

## Rincian Perbaikan Teknis

### 1. Triggers Duplicate Keyword Bug (`bot/handlers/triggers.py`, `bot/database.py`)
- **Masalah**: Tabel `triggers` tidak memiliki constraint `UNIQUE(keyword)`. Logika `cmd_selesai_trigger` yang mengandalkan blok `try: INSERT ... except: UPDATE ...` tidak pernah masuk ke blok `UPDATE` sehingga setiap kali trigger dengan keyword sama disimpan, baris duplikat selalu terbuat.
- **Solusi**:
  - Menambahkan `CREATE UNIQUE INDEX IF NOT EXISTS idx_triggers_keyword ON triggers(keyword)` saat inisialisasi basis data di `bot/database.py`.
  - Mengubah logika di `cmd_selesai_trigger` (`triggers.py`) menjadi pemeriksaan eksplisit `SELECT id FROM triggers WHERE keyword = ?`. Jika ada, lakukan `UPDATE triggers SET actions_json = ...`, jika belum ada lakukan `INSERT INTO triggers ...`.

### 2. Tugas Cross-Class IDOR (`bot/handlers/tugas.py`)
- **Masalah**: Callback inline `tsi:<task_id>` dan handler teks `handle_tugas_input` mengizinkan mahasiswa role `student`, `bem`, atau `maba` dari jurusan apapun untuk memulai submission tugas milik kelas/jurusan lain.
- **Solusi**:
  - Menambahkan verifikasi `_student_enrolled_class_ids(prof, role)` pada `cb_tugas` saat `data.startswith("tsi:")`. Jika `task["class_id"] not in enrolled_classes`, aksi langsung ditolak dengan pesan: *"Anda tidak terdaftar di kelas/matkul tugas ini."*
  - Menambahkan verifikasi yang sama pada `handle_tugas_input` sebelum jawaban dimasukkan ke `task_submissions`.

### 3. Unescaped HTML Entities di Telegram Messages (`bot/handlers/commands.py`, `bot/handlers/messages.py`)
- **Masalah**: Karakter `<` atau `>` pada nama pengguna atau teks submission maba menyebabkan Telegram API melempar error `400 Bad Request: Can't parse entities in message text`.
- **Solusi**:
  - `commands.py` (`cmd_cek_user`): Meng-escape `name`, `username`, dan `role` menggunakan `html.escape`.
  - `commands.py` (Penerusan pendaftaran maba ke `PENDAFTAR_CH_ID`): Meng-escape `name_tmp`, `reason_tmp`, dan `username_tmp`.
  - `commands.py` (`cmd_set_greeting` preview): Meng-escape placeholder nama dan username.
  - `messages.py` (`on_chat_member` group greeting): Meng-escape `user.first_name` dan `user.username`.

### 4. Concurrent Attendance Session Guard (`bot/handlers/attendance.py`, `bot/jobs.py`)
- **Masalah**: `open_attendance_session` secara sepihak mengeksekusi `UPDATE attendance_sessions SET closed_at = now WHERE class_id = ? AND closed_at IS NULL`. Jika admin/job membuka sesi saat sesi lama masih aktif, sesi lama ditutup tanpa rekap DM ke hadirin.
- **Solusi**:
  - Di `cb_open_presensi`: Memeriksa `db.get_open_session_for_class(conn, class_id)`. Jika sesi aktif sudah ada, batalkan pembukaan dan beri tahu admin melalui pesan alert: *"Sesi presensi untuk kelas ini sudah dibuka sebelumnya..."*.
  - Di `jobs.py` (`daily_staff_attendance_open` dan `daily_maba_attendance_open`): Memeriksa `get_open_session_for_class` sebelum membuka sesi baru agar sesi tidak ter-overwrite secara diam-diam.

### 5. Atomic Contract Sequence Generator (`bot/handlers/kontrak.py`, `bot/database.py`)
- **Masalah**: Nomor urut kontrak (`contract_seq_no`) dihitung melalui in-memory scan terhadap semua record di tabel `users`. Pembuatan kontrak simultan oleh beberapa staf menghasilkan collision nomor surat yang sama persis.
- **Solusi**:
  - Mengimplementasikan method `get_next_contract_seq(conn)` pada kelas `Database`.
  - Nomor urut disimpan dan di-increment secara atomik pada tabel `bot_settings` dengan key `contract_last_seq`. Jika belum pernah diinisialisasi, sistem secara otomatis men-seed nilai awal dari `max(contract_seq_no)` pada tabel `users`.
  - Di `kontrak.py`: Mengganti scan in-memory dengan pemanggilan `await db.get_next_contract_seq(conn)`.

### 6. Anti Self-Approval pada Profile Change Requests (`bot/handlers/commands.py`)
- **Masalah**: Staf dengan jabatan internal yang memiliki hak persetujuan profil (`can_approve_profile`, misal SDM) dapat menyetujui (`a:<id>:1`) pengajuan modifikasi profil miliknya sendiri tanpa second-party review.
- **Solusi**:
  - Pada penanganan callback `a:` di `commands.py`, sistem memeriksa apakah `uid == req["telegram_id"]`.
  - Jika ya dan pengguna bukan `owner`, callback ditolak dengan alert: *"❌ Anda tidak dapat memproses pengajuan profil Anda sendiri."*, dan status pengajuan tetap `pending`.

### 7. Menfess State Loss & Financial Protection (`bot/handlers/menfess.py`)
- **Masalah**: `execute_menfess` memotong saldo Agra di awal. Jika bot restart saat pengguna berada pada state `CONFIRM`, `context.user_data` kosong (`target_id` dan `message_text` bernilai `None`). Akibatnya, `html.escape(None)` melempar `TypeError`, bot crash, dan saldo pengguna terpotong tanpa refund.
- **Solusi**:
  - Menambahkan fungsi pembantu `_clear_menfess_data(context)` untuk membersihkan state obrolan pada pembatalan atau penyelesaian menfess.
  - Memvalidasi kelengkapan data `if not target_id or not message_text:` SEBELUM eksekusi pemotongan saldo (`deduct_agra_if_sufficient`). Jika state hilang, sesi dibatalkan dengan pesan informatif dan saldo Agra tetap 100% utuh.
  - Menjamin pembersihan state pada seluruh cabang keluar (`cancel`, `success`, `failure`).

### 8. Pendaftaran Standalone Command & Alias (`bot/handlers/register.py`)
- **Masalah**: Perintah `/laporan`, `/leaderboard`, dan `/pay` tercantum pada spesifikasi namun tidak terdaftar langsung di dispatcher PTB.
- **Solusi**:
  - Mendaftarkan `/pay` sebagai alias langsung untuk `commands.cmd_transfer`.
  - Mendaftarkan `/leaderboard` sebagai alias langsung untuk `commands.cmd_agratop`.
  - Mendaftarkan `/laporan` sebagai alias langsung untuk `commands.cmd_daftar`.

---

## Verifikasi & Hasil QA

Rangkaian unit & regression test dijalankan:
- `tests/test_deep_qa.py`: 9/9 tes PASSED (100%)
- Rangkaian penuh (`pytest tests/`): 14/14 tes PASSED (100%)
- Tidak ada regresi fungsional pada modul presensi, logika jurusan, mini games, maupun manajemen data.
