# Task 121: Deep QA Audit & Stabilization on Scope Filtering, Class Resolution, and Role Edge Cases

## Ringkasan Eksekutif
Berdasarkan audit mendalam (*deep code inspection*) terhadap seluruh alur resolusi kelas dinamis, evaluasi hak akses wewenang (*scope*) Dosen/Dekan, filter data, dan manajemen tugas, ditemukan 6 celah/bug potensial yang kini telah diperbaiki dan divalidasi dengan rangkaian uji otomatis (*40/40 tests passed*).

---

## 1. Temuan Masalah & Solusi Teknis

### Bug 1: Staf & Dosen Tidak Muncul pada `/daftar fakultas <fid>`
- **Masalah**: Pada `cmd_daftar` jenis `fakultas`, pencocokan hanya memeriksa `p.get("faculty") == fid`. Mahasiswa menyimpan fakultas pada field `faculty`, sedangkan staf/dosen/dekan menyimpannya pada `staff_faculty`. Akibatnya dosen dan staf fakultas tersebut tidak muncul.
- **Solusi**: Diperbarui menjadi `if p.get("faculty") == fid or p.get("staff_faculty") == fid: push_row(r, p)`.

### Bug 2: MABA (Pravesi) dan Panitia Ospek Hilang pada `/daftar kelas <cid>`
- **Masalah**:
  1. `student_enrolled_class_ids(p)` dipanggil tanpa argumen `role=r.get("role", "")`, sehingga evaluasi kelas `ospek_maba` untuk `ROLE_MABA` gagal dan menghasilkan list kosong.
  2. Pengecekan staf pengajar hanya membaca nilai mentah `teaching_classes`, tidak memanggil helper `lecturer_class_ids(p)` (sehingga Dosen dengan `staff_major`, Panitia Ospek `p_panitia_ospek`, dan Coach UKM tidak terdeteksi mengampu kelas tersebut).
- **Solusi**: Diperbarui menjadi:
  ```python
  enrolled = student_enrolled_class_ids(p, role=r.get("role", ""))
  teaching = lecturer_class_ids(p)
  if cid in enrolled or cid in teaching:
      push_row(r, p)
  ```

### Bug 3: Scope Exemption Dekan/Dosen untuk Kategori Publik & Charyarthi
- **Masalah**: Pada `cmd_daftar` dan `cmd_detail`, pengecualian scope dosen sebelumnya hanya memeriksa `if apply_scope and lec_mode and not (dean_mode and dean_fid)`. Jika pengguna memiliki hak Dekan dan menjalankan `/daftar publik` atau `/daftar charyarthi`, wewenang fakultas tetap dipaksakan (`apply_scope = True`). Karena data publik dan pelamar staf tidak memiliki fakultas atau kelas, filter scope mengeliminasi seluruh hasil dan menghasilkan "⚠️ Tidak ada pengguna di dalam lingkup wewenang Anda".
- **Solusi**: Kategori global (`publik`, `charyarthi`, `calon`, `pelamar`) kini secara eksplisit dibebaskan dari pembatasan fakultas/kelas untuk semua peninjau (Dekan maupun Dosen):
  ```python
  apply_scope = not is_global_admin and ((dean_mode and dean_fid) or (lec_mode and lec_cids))
  if apply_scope:
      if kind in ("publik", "charyarthi", "calon", "pelamar"):
          apply_scope = False
      elif lec_mode and not (dean_mode and dean_fid) and kind in ("dosen", "charya", "purva"):
          apply_scope = False
  ```

### Bug 4: MABA Menerima Tugas Kuliah Umum Mahasiswa Senior (`/tugas`)
- **Masalah**: Di `bot/handlers/tugas.py`, fungsi `_student_enrolled_class_ids` melakukan iterasi manual pada seluruh kelas dan menggunakan kondisi `if not m or m == major:`. Karena profil MABA belum memiliki jurusan (`major = None`), kelas kuliah umum (`umum_kk`, `umum_pd`) yang tidak memiliki atribut `majors` secara keliru masuk ke daftar kelas aktif MABA. MABA pun dapat melihat dan mengumpulkan tugas Kuliah Umum.
- **Solusi**: Menghapus duplikasi logika dan mendelegasikan resolusi kelas ke helper terpadu `student_enrolled_class_ids(profile, role=role)` dari `bot/handlers/common.py` (+ `club_enrolled`). Dengan ini, MABA terisolasi secara ketat hanya pada kelas `ospek_maba`.

### Bug 5: Tampilan `auto_class_enrolled` pada Profil
- **Masalah**: Pada `format_profile_field_value` di `common.py`, kondisi `if not m or m == major:` berpotensi memasukkan kelas non-jurusan jika `major` bernilai `None`.
- **Solusi**: Diperketat agar:
  - Jika `role == ROLE_MABA`: hanya menampilkan `ospek_maba`.
  - Jika `major` ada: hanya menampilkan kelas yang memiliki `item.majors == major` (di luar `umum_*` dan `ospek_maba`).
  - Jika profil belum memilih jurusan: mengembalikan `—`.

### Bug 6: Panitia Ospek & Coach pada Pencarian Scope Database
- **Masalah**: Di `Database.get_user_ids_by_scope` (`bot/database.py`), pencarian `class_id == "ospek_maba"` hanya mencocokkan `ROLE_MABA`, sedangkan staf yang menjabat Panitia Ospek (`p_panitia_ospek`) dan pelatih UKM (`d_coach`) tidak terpetakan ke kelas bersangkutan.
- **Solusi**: Menambahkan evaluasi `position_detail` untuk `p_panitia_ospek` dan `d_coach` pada filter `class_id`.

---

## 2. Pengujian & Verifikasi
- Menambahkan *unit test* baru di `tests/test_dosen.py` (`test_maba_and_student_enrolled_class_ids`).
- Menjalankan seluruh test suite (*full regression test*): **40 passed (100%)**.
