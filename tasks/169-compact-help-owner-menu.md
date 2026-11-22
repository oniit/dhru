# Task 169: Perampingan Menu /help_owner dan Eliminasi Duplikasi Sub-Menu

## Ringkasan Tugas
Menyederhanakan dan merapikan isi menu `/help_owner` agar tidak terjadi duplikasi informasi (*double info*). Detail sub-perintah dan tombol interaktif yang sudah disajikan secara mandiri di dalam sub-menu utama (seperti `/gencode`, `/generasi`, `/owner_reset`, `/export_kelulusan`) kini dirampingkan menjadi entri utama yang ringkas dan padat.

## Perubahan Teknis
- **`bot/handlers/commands.py` (`cmd_help_owner`)**:
  - Menggabungkan rincian pembuatan kode (`/gencode_avail`, `/gencode_warkat`, `/gencode_warkat_avail`) ke dalam satu entri utama `• /gencode` yang sudah memiliki menu interaktif.
  - Menggabungkan sub-perintah penutupan generasi (`/generasi_atur`, `/generasi_tutup`, `/setrole purna shishya/bem`) ke dalam entri `• /generasi` dan `• /setrole`.
  - Menggabungkan sub-perintah reset pengguna/agra ke dalam entri `• /owner_reset`.
  - Memadatkan opsi ekspor kelulusan (`/export_kelulusan [zip|sync]`, `/export_photos`).
  - Memadatkan entri moderasi grup (`/kick` & `/kicknot`).
  - Memadatkan entri rekrutmen staf (`/setting_charyarthi`, `/soal`, `/acc_charyarthi`, `/reject_charyarthi`).
  - Memadatkan entri repositori server (`/pull` & `/push [pesan]`).
  - Total baris berhasil dipangkas dari 25+ poin berulang menjadi 14 poin padat dan rapi, tanpa menghilangkan kompatibilitas pintasan cepat.

## Verifikasi & QA
- `pytest tests/test_help_and_export_json.py -v`: 4/4 PASSED (100%).
- `python tests/test_qa_master_audit.py`: 93/93 PASSED (100%).
