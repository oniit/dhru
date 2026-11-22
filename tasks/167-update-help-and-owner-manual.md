# Task 167: Pembaruan Menu /help dan Ensiklopedia /help_owner

## Ringkasan Tugas
Menyelaraskan menu panduan `/help` dan manual khusus Owner `/help_owner` dengan seluruh fitur, perintah, dan perubahan sistem terbaru (Warkat Kehormatan Prakarsha & Svatantra, Gencode Submenu, Generasi Unifikasi, PFP +1 Agra Reward, Kick multi-grup, serta seleksi staf Charyarthi).

## Perubahan Teknis
- **`bot/handlers/commands.py` (`help_for_role`)**:
  - Menambahkan `/kode [kode]` pada bagian **Perintah umum** agar pengguna mengetahui cara klaim Kode Akses registrasi maupun penukaran Warkat Kehormatan (Jalur Prakarsha & Jalur Svatantra).
  - Memperbarui deskripsi `/pfp` dengan catatan perolehan reward Agra (`/pfp — Forward post channel ke KEEP channel (+1 Agra)`).
  - Menambahkan section **Pendaftaran & Publik** khusus untuk peran `ROLE_PUBLIC` yang memuat `/charyarthi` dan `/maba`.
  - Menambahkan section **Komunitas & Agra** untuk pengguna terdaftar (mahasiswa, staf, admin, purna, bem) yang memuat perintah sosial: `/transfer`, `/leaderboard`, `/menfess`, `/menfess_read`, dan `/manosraya`.
  - Memperbarui section **Admin** dengan perintah `/kick` dan `/setting_charyarthi`.
  - Memastikan tautan `/help_owner` di akhir `/help` selalu muncul bagi pengguna dengan `role == ROLE_OWNER` maupun `is_owner(uid)`.
- **`bot/handlers/commands.py` (`cmd_help_owner`)**:
  - Menambahkan perintah `/kick` (multi-grup dynamic modal di private chat) dan `/kicknot` pada grup Manajemen Akun.
  - Memperbarui grup Kode Akses & Rekrutmen dengan perintah seleksi staf: `/setting_charyarthi`, `/soal [divisi]`, `/acc_charyarthi`, dan `/reject_charyarthi`.
  - Memperbarui deskripsi `/pfp` dengan reward +1 Agra.
  - Menjaga perintah generasi terbaru (`/generasi`, `/generasi_atur`, `/generasi_tutup`, `/setrole purna all`).

## Verifikasi & QA
- `pytest tests/test_help_and_export_json.py tests/test_warkat.py tests/test_public_menu.py tests/test_mass_setrole_purna.py -v`: 20/20 PASSED.
- `python tests/test_qa_master_audit.py`: 93/93 PASSED (0 bug, 0 error).
