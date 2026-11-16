# Task 152: Mass Setrole Purna & Tutup Generasi (Kelulusan Massal Shishya)

## Latar Belakang & Masalah
Pada saat pergantian generasi akademik (tutup generasi), seluruh Shishya aktif (peran `student`, dan pengurus `bem` yang merupakan mahasiswa) harus bertransisi menjadi alumni atau Purna Shishya (`purna`). Sebelumnya, admin/owner terpaksa mengetikkan perintah `/setrole purna @user1 @user2 ...` secara manual untuk puluhan atau ratusan mahasiswa atau me-reply pesan mereka satu per satu. Hal ini sangat merepotkan, tidak efisien, dan berisiko melewatkan anggota tertentu.

Selain itu, terdapat kebutuhan penting terkait integritas data akademik:
1. Ketika mahasiswa berubah peran menjadi `purna`, NIM resmi mereka (`student_id`) sebelumnya terhapus dari `profile_json`. Akibatnya, saat mereka meminta Transkrip Nilai (`/transkrip`) atau Ijazah (`/ijazah`) secara mandiri (*self-service*), pencarian via NIM gagal dan harus bergantung pada kecocokan nama profil mentah.
2. Indeks pada kolom `users.role` belum tersedia di DDL database, sehingga kueri pencarian mahasiswa aktif berpotensi memicu *Full Table Scan* yang boros kuota *rows read* Turso.

## Solusi yang Diimplementasikan
1. **Fitur Massal `/setrole purna <all|shishya|bem|massal|semua>`**:
   - Memperluas parser `parse_setrole_command` di `bot/setrole_parse.py` untuk mendeteksi kata kunci massal (`all`, `massal`, `shishya`, `student`, `students`, `shishyas`, `semua`, `bem`).
   - Menyediakan filter fleksibel:
     - `all` / `massal` / `semua`: meluluskan seluruh Shishya dan BEM sekaligus.
     - `shishya` / `student`: meluluskan hanya Shishya aktif.
     - `bem`: meluluskan hanya BEM.
2. **Perintah Dedikasi `/tutup_generasi` & `/tutupgenerasi`**:
   - Menambahkan perintah `/tutup_generasi` khusus Owner.
   - Jika dipanggil tanpa argumen, menampilkan ringkasan jumlah mahasiswa aktif yang akan diluluskan dan petunjuk konfirmasi.
   - Jika dipanggil dengan `/tutup_generasi konfirmasi`, langsung mengeksekusi kelulusan massal seluruh mahasiswa aktif.
3. **Gerbang Keamanan Eskalasi Peran (Strict Security Guard)**:
   - Fitur massal **HANYA** diizinkan untuk target role `purna`.
   - Upaya eksekusi massal untuk role lain (contoh: `/setrole admin all`, `/setrole public all`) secara ketat ditolak oleh sistem dengan notifikasi peringatan keamanan eksplisit.
   - Hanya akun Owner yang memiliki otorisasi untuk memanggil `/setrole` maupun `/tutup_generasi`.
4. **Preservasi Identitas Akademik Alumni & SKS Banking**:
   - Saat mahasiswa bertransisi ke `purna`, total SKS yang telah dikumpulkan otomatis dibukukan permanen ke `accumulated_sks`.
   - Kolom NIM (`student_id`) dipertahankan secara permanen di profil `purna` (didukung di `config/profile_fields.yaml`, `_apply_generated_profile_fields`, dan `_revalidate_filtered_choice_fields`).
   - Mata kuliah aktif (`class_enrolled`) dan UKM aktif (`club_enrolled`) dibersihkan dari profil sehingga bot langsung bersih dan siap menyambut mahasiswa generasi baru.
5. **Notifikasi dan Audit Trail**:
   - Bot mengirimkan notifikasi privat ucapan selamat kelulusan dan instruksi pencetakan `/ijazah` & `/transkrip` ke seluruh mahasiswa yang diluluskan secara bertahap (*throttled* dengan jeda 50 ms untuk mencegah *FloodWait* API Telegram).
   - Seluruh mutasi dicatat dalam tabel `audit_log` (`action: mass_set_role_purna`).
   - Bot menampilkan ringkasan eksekutif lengkap ke Owner berisi total lulusan, rincian per peran, dan daftar nama/NIM mahasiswa.
6. **Optimasi Indeks Turso**:
   - Menambahkan indeks permanen `CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)` di skema DDL statis dan runtime migration `Database.connect` guna menghemat kuota *rows read* Turso per aturan `AGENTS.md`.

## Perubahan Berkas Teknis
1. `config/profile_fields.yaml`:
   - Menambahkan peran `purna` ke dalam definisi `roles: [student, bem, purna]` untuk field `student_id` (NIM).
2. `bot/setrole_parse.py`:
   - Memperbarui dataclass `ParsedSetrole` dengan atribut `is_mass: bool = False` dan `mass_target: str | None = None`.
   - Menambahkan logika ekstraksi argumen teks massal tanpa `@mention` atau `reply_to_message`.
3. `bot/database.py`:
   - Menambahkan DDL indeks `idx_users_role` pada tabel `users(role)`.
   - Memperbarui `_apply_generated_profile_fields` agar mempertahankan `student_id` saat `role == ROLE_PURNA`.
   - Memperbarui `Database.set_role` agar tidak melepaskan (*pop*) `student_id` alumni.
   - Menambahkan metode `Database.mass_set_role_purna(conn, actor_id, target_type)` untuk eksekusi batch transisi peran, akumulasi SKS, pembersihan kelas, dan audit logging.
4. `bot/handlers/commands.py`:
   - Memperbarui `_revalidate_filtered_choice_fields` agar mengecualikan `student_id` dari pembersihan profil alumni.
   - Mengintegrasikan penanganan `parsed.is_mass` pada `cmd_setrole` lengkap dengan verifikasi keamanan `ROLE_PURNA`, eksekusi database, notifikasi throttled, dan ringkasan eksekutif.
   - Mengimplementasikan `cmd_tutup_generasi` sebagai alur interaktif/konfirmasi penutupan generasi.
5. `bot/handlers/register.py`:
   - Mendaftarkan handler `tutup_generasi` dan `tutupgenerasi` ke instance Telegram Application.
6. `docs/commands.md` & `docs/architecture.md`:
   - Mendokumentasikan sintaks massal `/setrole purna <target>`, `/tutup_generasi`, serta arsitektur kelulusan massal dan preservasi NIM alumni.
7. `tests/test_mass_setrole_purna.py`:
   - Mengembangkan test suite komprehensif (6/6 suites PASS) yang memverifikasi parser, proteksi keamanan, akumulasi SKS, preservasi NIM, filter shishya/bem, dan integrasi transkrip mandiri.

## Hasil Pengujian & Verifikasi
- Test Suite Baru: `tests/test_mass_setrole_purna.py` -> **6/6 Suites PASSED** (0.64s).
- Production QA Master Audit: `tests/test_qa_master_audit.py` -> **67/67 Tests PASSED** (0.81s).
- Zero regression pada seluruh alur ekonomi Agra, presensi, tugas, kartu KTS, dan dokumen kelulusan.
