# Task 123: Pengetatan Tutup Presensi Umum, Filter Grup Dinamis /kick PM, dan Akses Presensi Yaksa bagi Āchāryata

## Ringkasan Eksekutif
Berdasarkan permintaan pengguna, dilakukan 3 pembaruan penting pada sistem presensi dan manajemen grup:
1. **Strict Close Presensi Umum (`event_bebas`)**: Membatasi penutupan presensi umum hanya dapat dilakukan oleh pembuat sesi bersangkutan atau pihak Admin/Owner, guna mencegah anggota lain menutup sesi presensi secara sembarangan.
2. **Filter Target Grup Dinamis pada `/kick` PM**: Memperbarui flow perintah `/kick` ketika dipanggil via Private Message (PM) bot oleh Owner/Admin/Sekre agar hanya menampilkan daftar tombol grup di mana user target benar-benar bergabung (bukan seluruh list grup bot).
3. **Akses Presensi Yaksa untuk Āchāryata (`pembina` / `d_pembina`)**: Memperluas hak wewenang presensi `bem_manual` (Presensi Yaksa) agar Pembina BEM (Āchāryata) dapat membuka sesi, mencatatkan kehadiran, dan melihat rekap kehadiran Yaksa.

---

## 1. Rincian Masalah & Perubahan Teknis

### A. Pengetatan Tutup Presensi Umum (`event_bebas`)
- **Masalah**: Pada implementasi sebelumnya (Task 079), kelas `event_bebas` dimasukkan ke dalam `presence_allowed_class_ids` untuk semua peran terdaftar (non-public) agar siapa pun dapat membuka presensi umum. Namun efek sampingnya, fungsi `cmd_tutup_presensi` mengevaluasi `if sess["class_id"] not in allowed:`. Karena `event_bebas` ada di dalam list wewenang setiap user, anggota mana pun dapat mengeksekusi `/presensi tutup <id>` terhadap sesi umum yang dibuat orang lain.
- **Solusi**: Di `bot/handlers/attendance.py` pada fungsi `cmd_tutup_presensi`, ditambahkan validasi khusus untuk `sess["class_id"] == "event_bebas"`:
  ```python
  if sess["class_id"] == "event_bebas":
      if row["role"] not in (ROLE_OWNER, ROLE_ADMIN) and sess["opened_by"] != update.effective_user.id:
          await update.message.reply_text(
              "Hanya pembuat sesi atau Admin/Owner yang dapat menutup presensi umum ini."
          )
          return
  ```
  Pengguna biasa yang bukan pembuka sesi langsung ditolak dengan pesan peringatan yang informatif.

### B. Filter Target Grup Dinamis pada `/kick` PM
- **Masalah**: Ketika Owner/Admin menjalankan `/kick @user` atau `/kick <id>` melalui obrolan pribadi (PM) bot, sistem sebelumnya mengambil seluruh grup aktif bot dari database (`list_active_bot_chats`) dan membuat tombol untuk seluruh grup tersebut, bahkan grup yang tidak dihuni oleh target.
- **Solusi**: Di `bot/handlers/commands.py` pada `cmd_kick` bagian cabang PM (`not is_group`):
  1. Melakukan inspeksi keanggotaan real-time Telegram menggunakan `context.bot.get_chat_member(chat_id=c_id, user_id=target["id"])` yang dieksekusi secara konkuren via `asyncio.gather`.
  2. Memfilter list grup hanya untuk grup di mana `m.status not in ("left", "kicked")`.
  3. Jika target tidak berada di grup aktif manapun: mengirim respons `⚠️ <b>{target['name']}</b> tidak ditemukan di grup manapun yang terhubung dengan bot.`.
  4. Jika target ditemukan pada 1 atau lebih grup: menampilkan *inline keyboard* yang HANYA memuat grup-grup tersebut plus tombol `Batal`.

### C. Pembina BEM (Āchāryata) Dapat Membuka Presensi Yaksa
- **Latar Belakang**: Sesuai konfigurasi jabatan di `config/choices.yaml`, Pembina BEM memiliki ID detail `d_pembina` dan posisi `pembina` (Āchāryata). Presensi Yaksa (`bem_manual`) sebelumnya hanya dapat dibuka oleh akun dengan role murni `ROLE_BEM` (atau Admin/Owner).
- **Solusi**:
  1. Di `bot/handlers/common.py`, membuat helper `is_acharyata_profile(profile: dict | None) -> bool`:
     Mengecek apakah `"d_pembina"` ada di jabatan (`get_user_jabatans`) atau `profile.get("position") == "pembina"`.
  2. Memperbarui `presence_allowed_class_ids`:
     ```python
     if role == ROLE_BEM or is_acharyata_profile(p):
         has_access = True
         ids.append("bem_manual")
     ```
  3. Memperbarui handler `cmd_hadir`, `cb_attendance_action`, dan `cmd_rekap_hadir` di `bot/handlers/attendance.py` agar menyertakan `or is_acharyata_profile(profile)` pada pengecekan hak `bem_manual`.

---

## 2. Pengujian & Verifikasi
- Dibuat unit test komprehensif di `tests/test_presensi_strict_and_kick.py`:
  - `test_acharyata_profile_and_presence_scope`: Memvalidasi pengenalan profil Āchāryata dan penambahan `bem_manual` pada wewenang presensi.
  - `test_strict_tutup_presensi_umum`: Memvalidasi penolakan penutupan sesi umum oleh orang asing, serta keberhasilan penutupan oleh pembuat sesi dan admin/owner.
  - `test_cmd_kick_pm_only_shows_target_groups`: Memvalidasi pemfilteran dinamis tombol grup pada eksekusi `/kick` via PM.
- Hasil uji: **3/3 passed (100%)**.
