# Task 171: Cmd Reload Graceful Fallback & VPS Sudo Handling

## 1. Masalah & Penyebab (Root Cause)
1. **Sudo Password Prompt pada VPS**:
   - Di server VPS, perintah `sudo systemctl restart botdhru` membutuhkan password pengguna Linux (`administrator`) karena aturan `NOPASSWD` belum ditambahkan di file sudoers.
   - Ketika dipanggil melalui Telegram command `/reload`, proses bot berjalan di latar belakang (daemon) tanpa terminal interaktif (TTY). Akibatnya, `sudo` gagal dan menolak eksekusi, atau mematikan proses tanpa sempat menyalakan proses baru, menyebabkan bot berhenti (*dead*).
   - Di terminal SSH VPS, pengguna mendapati pesan `[sudo] password for administrator: ` dan `botdhru.service` tidak aktif di CGroup systemd.
2. **Ketiadaan Output pada `systemctl start`**:
   - Saat pengguna menjalankan `sudo systemctl start botdhru`, systemd tidak menghasilkan keluaran teks apa pun (*silent exit*) saat perintah diterima.

## 2. Solusi yang Diterapkan
1. **Fallback Otomatis pada `cmd_reload` (`bot/handlers/commands.py`)**:
   - Memperbarui perintah `cmd_reload` untuk mencoba `sudo -n systemctl restart botdhru` (`-n` = non-interactive, langsung keluar jika butuh password dan tidak memblokir event loop).
   - Menambahkan *in-place restart fallback* menggunakan `os.execv(sys.executable, [sys.executable] + sys.argv)` sehingga bot dapat me-reload dirinya sendiri tanpa memerlukan akses root atau konfigurasi sudo sama sekali.
   - Memperketat pengecekan wewenang: `is_owner(uid) or (row and row.get("role") == ROLE_OWNER)`.
2. **Panduan Konfigurasi Sudoers untuk VPS**:
   - Menambahkan petunjuk satu baris untuk memberikan izin `NOPASSWD` pada `systemctl` untuk user `administrator` di `/etc/sudoers.d/botdhru`.
3. **Pengujian Unit Test**:
   - Menambahkan `test_cmd_reload` di `tests/test_help_and_export_json.py` yang memverifikasi pembatasan role non-owner, pemanggilan non-interaktif `systemctl`, dan mekanisme fallback `os.execv`. Seluruh 5 unit test dan 93 QA audit tests lulus 100%.
