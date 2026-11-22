# Task 170: Pembersihan Commit Kotor VPS, Update .gitignore, dan Penambahan /pull force

## Ringkasan Tugas
Menghapus commit kotor `d51d2979f3dd0c37b2bc0a1c4b7207294361e5ac` dari GitHub yang tidak sengaja menyertakan direktori `venv/` (12.638 file) dan `dump.sql` dari server VPS. Memperbarui `.gitignore` agar tidak meloloskan file virtual environment, dump SQL, dan file sementara lainnya. Menambahkan dukungan perintah `/pull force` agar repositori di server VPS dapat diselaraskan paksa (`git reset --hard origin/main`) tanpa harus SSH manual.

## Tindakan yang Dilakukan
1. **Inspeksi Commit Kotor**:
   - Commit `d51d2979f3dd0c37b2bc0a1c4b7207294361e5ac` diverifikasi hanya memuat folder `venv/` (12.638 file binary & library Python) dan `dump.sql`.
2. **Pembaruan `.gitignore`**:
   - Menambahkan:
     - `venv/`
     - `.venv/`
     - `env/`
     - `*.sql`
     - `dump.sql`
     - `.restart.json`
3. **Pembersihan Repositori GitHub**:
   - Menimpa dan menghapus commit `d51d297` dari GitHub menggunakan force push dari branch lokal yang bersih (`git push origin main --force`).
4. **Pembaruan Perintah `/pull force`**:
   - Memperbarui `cmd_pull` di `bot/handlers/commands.py`:
     - Jika dipanggil dengan `/pull force` atau `/pull reset`, bot secara otomatis mengeksekusi `git fetch origin` lalu `git reset --hard origin/main`.
     - Ini memungkinkan Owner menyelaraskan repositori VPS yang divergen langsung dari chat Telegram tanpa perlu masuk ke terminal SSH VPS.

## Verifikasi
- Status branch lokal dan remote `origin/main` tersinkronisasi bersih di commit `50a305d`.
- 12.638 file `venv/` dan `dump.sql` telah sepenuhnya bersih dari riwayat `origin/main` di GitHub.
- Seluruh 4/4 tes pytest dan 93/93 tes QA master audit lulus 100%.
