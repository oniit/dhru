# Task 106: QA Bug Fixes - Purva SKS Banking, Dosen Jabatan Scope, dan Modular Import Refactoring

## Ringkasan Eksekutif
Berdasarkan instruksi QA mendalam (`docs/qa.md`), seluruh rangkaian sistem dan pengujian unit dievaluasi secara menyeluruh. Ditemukan beberapa kegagalan tes dan potensi celah runtime yang berhasil diselesaikan dan diverifikasi:
1. **Purva SKS Banking & Academic Pruning (`bot/database.py`, `tests/test_purva.py`)**: Pembersihan field perkuliahan aktif saat mahasiswa bertransisi ke role `purva` serta pembatasan auto-enrollment kelas umum hanya untuk role aktif (`student` dan `bem`).
2. **Dosen / Jabatan Scope Resolver (`bot/handlers/common.py`, `tests/test_dosen.py`)**: Penambahan fallback pencarian jabatan struktural ke `bem_position` selain `position_detail`.
3. **Pembersihan Import Redundan & Pencegahan `UnboundLocalError` (`bot/handlers/messages.py`, `bot/jobs.py`)**: Migrasi impor lokal di dalam tubuh fungsi ke tingkat modul (*module-level imports*) untuk mencegah variabel lokal membayangi (*shadowing*) impor modul.
4. **Harden Idempotensi Tes LPM (`tests/test_promo_lpm.py`)**: Penambahan sanitasi data otomatis pada tabel `promo_verifications` sebelum dan sesudah pengujian agar tes dapat dijalankan berulang kali tanpa konflik data unik.

Seluruh 28 unit test pada folder `tests/` kini lulus 100% (`28 passed`).

---

## Rincian Teknis & Perubahan Kode

### 1. BUG-QA-01: Purva SKS Banking & Field Pruning
- **File**: `bot/database.py`, `tests/test_purva.py`
- **Akar Masalah**:
  - Saat akun diubah menjadi `purva` melalui `set_role`, atribut perkuliahan aktif (`major`, `class_enrolled`, `club_enrolled`, `student_id`) tidak dibersihkan dari profil aktif, sehingga data alumni masih tercampur dengan data mahasiswa aktif.
  - Di `_apply_generated_profile_fields`, kelas umum (`umum_kk`, `umum_pd` yang tidak memiliki `item_major`) secara otomatis di-enroll ke semua peran tanpa memandang apakah pengguna adalah alumni, sehingga alumni mendapatkan tambahan 4 SKS baru di atas SKS historis mereka.
- **Solusi**:
  - Di `set_role`, menambahkan pembersihan eksplisit:
    ```python
    if new_role == ROLE_PURVA:
        current.pop("major", None)
        current.pop("class_enrolled", None)
        current.pop("club_enrolled", None)
        current.pop("student_id", None)
    ```
  - Di `_apply_generated_profile_fields`, membatasi auto-enrollment kelas umum hanya jika role pengguna adalah `student` atau `bem`:
    ```python
    if role in (ROLE_STUDENT, ROLE_BEM):
        final_classes.append(item["id"])
    ```
  - Memperbaiki perhitungan assertion pada `tests/test_purva.py` agar selaras dengan total SKS yang diakumulasikan (12 SKS sebelumnya + 12 SKS baru = 24 SKS).

---

### 2. BUG-QA-02: Dosen / Jabatan Scope Fallback
- **File**: `bot/handlers/common.py`, `tests/test_dosen.py`
- **Akar Masalah**:
  - Fungsi `get_user_jabatans` hanya memeriksa field `position_detail`. Pada alur pendaftaran dan skema data tertentu, data jabatan BEM/staf tersimpan di bawah field `bem_position`.
- **Solusi**:
  - Menambahkan pengecekan terhadap `bem_position` ke dalam daftar jabatan yang dikembalikan oleh `get_user_jabatans`:
    ```python
    pos_alt = profile.get("bem_position")
    if pos_alt and pos_alt not in result:
        result.append(pos_alt)
    ```

---

### 3. BUG-QA-03: Modular Import Refactoring & Local Shadowing Elimination
- **File**: `bot/handlers/messages.py`, `bot/jobs.py`
- **Akar Masalah**:
  - Adanya impor di dalam blok fungsi (seperti `from telegram import InlineKeyboardMarkup, InlineKeyboardButton`, `import html as html_module`, `import logging`, `import time`, dan `from .common import award_lengkapi_agra`) menyebabkan Python menafsirkan nama-nama tersebut sebagai variabel lokal fungsi.
  - Jika nama tersebut diakses sebelum baris impor lokal dieksekusi, Python melempar runtime exception `UnboundLocalError`.
- **Solusi**:
  - Memindahkan seluruh modul eksternal dan kelas utilitas ke bagian header file di `bot/handlers/messages.py`:
    - `from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember`
    - `import html`
    - `from bot.settings import (..., MABA_CH_IDS, is_admin_elevated)`
    - `from .common import (..., award_lengkapi_agra, build_maba_verification_text, get_active_charyarthi_divisions)`
  - Mengganti pemanggilan lokal `import logging; logging.getLogger(__name__)` dengan instance logger modul `log.warning` dan `log.error`.
  - Mengonsolidasikan impor `logging` dan `time` di header `bot/jobs.py`.

---

### 4. Idempotensi Pengujian LPM
- **File**: `tests/test_promo_lpm.py`
- **Solusi**:
  - Menambahkan pembersihan record pada tabel `promo_verifications` (`DELETE FROM promo_verifications WHERE link = ?`) sebelum dan sesudah eksekusi `test_lpm_cmd_interactive_responses`. Hal ini menjamin pengujian tidak gagal akibat constraint *link already claimed* ketika dijalankan berkali-kali pada remote Turso DB.

---

## Verifikasi & Hasil QA

Pengujian otomatis dijalankan dengan perintah `pytest tests/ -v`:
```text
tests/test_all.py::test_all_features_suite PASSED                        [  3%]
tests/test_charyarthi.py::test_charyarthi_flow PASSED                    [  7%]
tests/test_charyarthi.py::test_charyarthi_acc_and_rej_callback PASSED    [ 25%]
tests/test_dosen.py::test_lecturer_class_ids_and_scope PASSED            [ 71%]
tests/test_logic.py::test_logic_all PASSED                               [ 75%]
tests/test_promo_lpm.py::test_verify_lpm_link_embed_real_link PASSED     [ 89%]
tests/test_promo_lpm.py::test_lpm_cmd_interactive_responses PASSED       [ 92%]
tests/test_purva.py::test_purva_sks_banking_and_fields PASSED            [ 96%]
tests/test_runner.py::test_all_commands_runner PASSED                    [100%]
================= 28 passed, 2 warnings in 217.56s =================
```
Semua 28 suite pengujian berhasil dilewati tanpa error.
