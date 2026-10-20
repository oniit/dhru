# Task 124: Deep QA Audit & Stabilization on Recent Changes (Presensi Umum, /kick PM, and Acharyata Yaksa)

## Ringkasan Eksekutif
Berdasarkan permintaan QA menyeluruh (*deep quality assurance*), telah dilakukan audit mendalam dan pengujian komprehensif terhadap 3 area fitur terbaru:
1. **Pengetatan Presensi Umum (`event_bebas`)**: Validasi wewenang penutupan sesi.
2. **Filter Dinamis & Pengamanan `/kick` PM**: Pengecekan keanggotaan grup target serta re-auth pada callback query.
3. **Wewenang Lengkap Āchāryata pada Presensi Yaksa (`bem_manual`)**: Pembukaan, absensi, dan rekapitulasi.

---

## 1. Temuan Audit QA & Penyempurnaan yang Diterapkan

### A. Tipe Data `opened_by` dan Wewenang Elevated Admin pada Penutupan Presensi Umum
- **Potensi Masalah**: Kolom `opened_by` di database dapat dibaca sebagai tipe integer maupun string oleh driver tertentu. Jika dibandingkan langsung `sess["opened_by"] != update.effective_user.id`, perbandingan string `"12345" != 12345` dapat menghasilkan `True` dan secara keliru memblokir pembuat sesi asli. Selain itu, admin/owner yang memiliki `is_admin_elevated` (berdasarkan `OWNER_ID` atau `ADMIN_IDS`) harus dipastikan selalu dapat menutup sesi meskipun role di database belum sinkron.
- **Perbaikan**: Di `bot/handlers/attendance.py`:
  ```python
  if sess["class_id"] == "event_bebas":
      from bot.settings import is_admin_elevated
      opened_by = int(sess.get("opened_by") or 0)
      if (
          row["role"] not in (ROLE_OWNER, ROLE_ADMIN)
          and not is_admin_elevated(update.effective_user.id)
          and opened_by != update.effective_user.id
      ):
          await update.message.reply_text(
              "Hanya pembuat sesi atau Admin/Owner yang dapat menutup presensi umum ini."
          )
          return
  ```
  Dan pada `_record_hadir`, pengecekan pembuat sesi juga dikonversi secara aman: `int(sess.get("opened_by") or 0) == uid`.

### B. Celah Re-Auth pada Callback `/kick` (`on_kick_callback`)
- **Potensi Masalah**: Di `bot/handlers/commands.py`, fungsi `on_kick_callback` mengeksekusi `_do_kick` tanpa melakukan re-evaluasi wewenang terhadap `query.from_user.id`. Jika pesan inline keyboard diforward atau diakses oleh pengguna tidak berwenang, tombol dapat diklik oleh siapa pun.
- **Perbaikan**: Menambahkan verifikasi hak akses pada `on_kick_callback`:
  ```python
  caller_id = query.from_user.id
  caller_row = await user_row(conn, db, caller_id)
  caller_prof = profile_from_row(caller_row) if caller_row else {}
  pos = caller_prof.get("position_detail")
  is_sekre = "d_sekre" in pos if isinstance(pos, list) else pos == "d_sekre"
  if not (is_admin_elevated(caller_id) or is_sekre):
      await query.edit_message_text("⛔ Anda tidak memiliki izin untuk melakukan tindakan ini.")
      return
  ```

### C. Siklus Lengkap Presensi Yaksa untuk Āchāryata
- **Audit**:
  1. *Buka Sesi*: `presence_allowed_class_ids` memasukkan `bem_manual` jika `is_acharyata_profile(p)` bernilai `True`.
  2. *Isi Kehadiran*: `cmd_hadir` dan `cb_attendance_action` memasukkan `bem_manual` ke dalam `user_classes` bagi Āchāryata, sehingga absensi Hadir/Izin diterima dan bonus Agra tercatat.
  3. *Rekap*: `cmd_rekap_hadir` mengizinkan akses rekap spesifik sesi maupun `all`/`total` bagi Āchāryata.

---

## 2. Hasil Pengujian Otomatis
Pengujian dijalankan melalui Pytest:
- **`tests/test_presensi_strict_and_kick.py`**:
  - `test_acharyata_profile_and_presence_scope`: **PASSED**
  - `test_strict_tutup_presensi_umum`: **PASSED**
  - `test_cmd_kick_pm_only_shows_target_groups`: **PASSED**
  - `test_on_kick_callback_auth_and_cancel`: **PASSED**
  - `test_acharyata_can_attend_and_rekap_yaksa`: **PASSED**
  Total: **5/5 passed (100%)**.
- **Core Regression Test Suite** (`test_dosen.py`, `test_pindah_data.py`, `test_auto_close_presensi.py`, `test_logic.py`):
  Total: **7/7 passed (100%)**.
