# Task 120: Fix Auto Major Class Resolution in Lecturer Scope and /daftar Filters

## Latar Belakang & Masalah
Pada pembaruan sebelumnya (Tasks 078: Chained Major Selection), sistem pendaftaran mahasiswa dirombak agar mahasiswa cukup memilih **Jurusan** (`major`) secara langsung, tanpa perlu memilih kelas manual satu per satu (`class_enrolled`). Kelas-kelas perkuliahan (misalnya Dasar Fotografi `df` dan Teknik Fotografi `tf` untuk Jurusan Fotografi `sf`) otomatis dipetakan secara dinamis berdasarkan jurusan mahasiswa tersebut.

Namun, fungsi evaluasi hak akses dan filter data:
1. `user_in_lecturer_scope(p, class_ids)` di `bot/handlers/common.py`
2. `user_in_dean_faculty_scope(p, faculty_id)` di `bot/handlers/common.py`
3. Filter `kind == "kelas"` di `bot/handlers/commands.py` (`cmd_daftar`)
4. Filter `filter_type == "kelas"` di `bot/handlers/commands.py` (`cmd_all`)

masih hanya mengevaluasi data mentah `p.get("class_enrolled")` yang kini bernilai `None`/kosong pada profil mahasiswa baru.

### Dampak Bug:
- Saat Dosen (yang mengampu kelas matkul jurusan bersangkutan, misal Dosen Fotografi yang mengampu `df` dan `tf`) mengecek `/daftar jurusan sf`, seluruh 9 mahasiswa Jurusan Fotografi disaring keluar (*filtered out*) karena dianggap tidak terdaftar di kelas ajar dosen tersebut. Akibatnya bot menampilkan respon `Kosong.`.
- Perintah `/daftar kelas <cid>` juga tidak memunculkan mahasiswa yang otomatis terdaftar di kelas tersebut melalui jurusannya.

---

## Solusi & Perubahan Teknis

### 1. Helper Universal Resolusi Kelas Mahasiswa (`bot/handlers/common.py`)
Menambahkan fungsi `student_enrolled_class_ids(profile: dict | None) -> list[str]`:
- Mengambil kelas manual jika ada (`class_enrolled`).
- Menelusuri seluruh kelas pada `CHOICES["classes"]` yang memiliki nilai `majors` cocok dengan `profile.get("major")`.
- Mengembalikan gabungan set seluruh ID kelas yang aktif diambil mahasiswa.

### 2. Pembaruan `user_in_lecturer_scope` & `user_in_dean_faculty_scope` (`bot/handlers/common.py`)
- Mengganti pembacaan `p.get("class_enrolled")` menjadi `student_enrolled_class_ids(p)`.
- Kini mahasiswa jurusan `sf` otomatis terdeteksi mengambil kelas `df` dan `tf`, sehingga sah berada dalam lingkup Dosen pengampu `df`/`tf`.

### 3. Pembaruan `cmd_daftar` & `cmd_all` (`bot/handlers/commands.py`)
- Pada filter `jurusan`: Menambahkan pencocokan `staff_major` agar dosen/staf yang memiliki homebase jurusan juga terdata.
- Pada filter `kelas`: Menggunakan `student_enrolled_class_ids(p)` agar mahasiswa yang terdaftar otomatis via jurusan ikut tercatat saat admin/dosen mengecek `/daftar kelas <cid>`.
- Pada `cmd_all` filter `kelas`: Menggunakan `student_enrolled_class_ids(u_prof)` agar mention tagall per kelas menjangkau seluruh mahasiswa jurusan tersebut.

### 4. Pengujian Otomatis (`tests/test_dosen.py`)
- Menambahkan *test assertion* pada `tests/test_dosen.py` untuk memvalidasi bahwa mahasiswa dengan profil hanya berisi `major: sf` (tanpa `class_enrolled`) secara otomatis lolos evaluasi `user_in_lecturer_scope` untuk kelas `df` dan `tf`, serta ditolak untuk kelas jurusan lain (`kd`).

### 5. Pesan Umpan Balik Informatif Scope (`cmd_daftar` di `commands.py`)
- Mengganti balasan ambigu `Kosong.` ketika data sebenarnya ada di database namun disaring oleh batasan hak akses Dosen/Dekan.
- Bot kini memberikan penjelasan eksplisit:
  `⚠️ Tidak ada pengguna di dalam lingkup wewenang Anda.`
  `💡 Catatan: Data ini ada di sistem (N pengguna), namun Anda dibatasi hanya untuk melihat pengguna di lingkup Anda (Kelas Ajar / Fakultas).`
- Menambahkan label jumlah pada header jika daftar difilter: `(Dibatasi lingkup Anda: X dari Y total)`.

