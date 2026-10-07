# Task 092: Deep Production QA Audit & Reproduksi Celah Sistem

## Ringkasan Pekerjaan
Melakukan QA level produksi mendalam sesuai dengan instruksi `docs/qa.md` terhadap seluruh sistem bot (handlers, FSM/state, otorisasi/role, database Turso, dan komunikasi Telegram). Membangun automated reproduction test suite di `tests/test_deep_qa.py` untuk menguji bug nyata, security bypass, IDOR, dan race conditions tanpa mengubah kode produksi.

## Hasil Temuan Teknis & Pengujian

1. **Triggers Table Lacks UNIQUE Constraint (`bot/handlers/triggers.py`)**:
   - Skema tabel `triggers` tidak memiliki konstrain `UNIQUE` pada kolom `keyword`.
   - Kode di `cmd_selesai_trigger` menggunakan pola `try: INSERT ... except: UPDATE ...`.
   - Karena INSERT tidak pernah gagal pada keyword yang sama, blok `except` tidak pernah terpanggil dan selalu meng-insert baris duplikat. Saat pencarian trigger dijalankan, data lama selalu terambil lebih dulu.

2. **IDOR / Cross-Class Task Submission Bypass (`bot/handlers/tugas.py`)**:
   - Handler callback `tsi:<task_id>` hanya memeriksa apakah role user adalah `student`/`bem`/`maba`.
   - Sistem melewatkan pengecekan `_student_enrolled_class_ids(profile, role)`.
   - Akibatnya, mahasiswa dari jurusan manapun (misal Seni Musik) dapat mengirim tugas dari jurusan lain (misal Kimia) atau tugas ospek maba, lalu memperoleh reward Agra saat di-ACC.

3. **Unescaped HTML Injection & Parse Errors (`bot/handlers/commands.py` & `messages.py`)**:
   - `cmd_cek_user` tidak membungkus `full_name` dengan `html.escape()`.
   - Pada pendaftaran maba (`commands.py:989`), `full_name` dan `join_reason` diinterpolasi langsung ke HTML tanpa escape saat diteruskan ke `PENDAFTAR_CH_ID`.
   - Karakter `<` atau `>` pada nama/alasan menyebabkan Telegram API melempar error `400 Bad Request: Can't parse entities in message text`.

4. **Silent Overwrite on Concurrent Attendance Sessions (`bot/handlers/attendance.py`)**:
   - `open_attendance_session` secara otomatis mengeksekusi `UPDATE attendance_sessions SET closed_at = ? WHERE class_id = ? AND closed_at IS NULL`.
   - Sesi lama ditutup secara sepihak di database tanpa memicu alur notifikasi rekap DM (`cmd_tutup_presensi`). Tombol inline pada pesan pengumuman lama menjadi basi ("Sesi tidak valid atau sudah ditutup").

5. **Race Condition pada Nomor Surat Kontrak (`bot/handlers/kontrak.py`)**:
   - Nomor urut surat (`contract_seq_no`) dihitung via linear in-memory scan terhadap seluruh `profile_json` di tabel `users` (`max_seq + 1`).
   - Eksekusi serentak oleh dua staf menghasilkan nomor urut dan nomor surat yang sama persis karena tidak adanya atomic sequence generator / sequence lock.

6. **Self-Approval Privilege Flaw pada Profile Requests (`bot/handlers/commands.py`)**:
   - `can_approve_profile` mengizinkan user dengan jabatan internal tertentu (seperti `d_umum_sdm`).
   - Callback `a:ID:1` tidak memeriksa apakah `decided_by == target_id`.
   - Staf SDM dapat mengajukan perubahan data dirinya sendiri dan langsung menyetujuinya tanpa tinjauan pihak kedua.

7. **State Loss & Financial Loss pada Menfess (`bot/handlers/menfess.py`)**:
   - `execute_menfess` melakukan pemotongan saldo Agra secara atomik di awal, namun jika bot baru saja restart saat user berada di state `CONFIRM`, `context.user_data` kosong.
   - Eksekusi crash pada `target_name.replace` dan melempar unhandled exception sebelum channel message / DB insert. Saldo Agra user terpotong tanpa ada proses refund otomatis.

8. **Kesenjangan Spesifikasi Perintah (Spec Gap)**:
   - Perintah `/laporan`, `/leaderboard`, dan `/pay` yang tercantum pada tabel spesifikasi `docs/qa.md` tidak terdaftar sebagai standalone command di Application dispatcher PTB (`/leaderboard` terintegrasi di `/agra top`, `/pay` di `/transfer`, dan `/laporan` belum diimplementasikan).
