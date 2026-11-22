# Task 168: Implementasi Perintah /push untuk Sinkronisasi Data VPS ke Git

## Ringkasan Tugas
Menambahkan perintah `/push [pesan]` (khusus Founder / Owner) yang berfungsi melengkapi `/pull`, memungkinkan Owner melakukan sinkronisasi dua arah langsung dari chat bot Telegram. Fitur ini dirancang agar data baru atau perubahan yang terjadi di server VPS (misalnya arsip kelulusan `data/graduation_records.json` atau file konfigurasi) dapat di-commit dan di-push kembali ke repositori GitHub secara otomatis, sehingga pengelola dapat menariknya (`git pull`) ke komputer lokal.

## Perubahan Teknis
- **`bot/handlers/commands.py` (`cmd_push`)**:
  - Validasi otentikasi eksklusif Owner (`is_owner(uid)` atau `role == ROLE_OWNER`).
  - Eksekusi dipindahkan ke off-thread worker (`_async_to_thread`) dengan timeout terukur agar tidak pernah memblokir asyncio event loop Telegram (mencegah bot terkesan "mati"/freeze).
  - Menjalankan `git status --porcelain` untuk mendeteksi perubahan atau berkas baru.
  - Jika terdapat perubahan:
    - Membaca pesan commit kustom dari argumen (`/push [pesan]`), atau membuat default `sync: auto-sync VPS data (<timestamp>)`.
    - Menjalankan `git add -A`.
    - Menjalankan `git commit -m "[pesan]"` dengan fallback `-c user.name=Dhruva Bot` dan `-c user.email=bot@dhruva.internal` agar commit tidak gagal jika server VPS belum menyetel global identity.
  - Menjalankan `git push` dengan konfigurasi `-c http.postBuffer=524288000` (buffer 500MB) untuk mencegah error `502 Bad Gateway` saat payload data dikirim via HTTPS ke reverse proxy GitHub.
  - Mendukung otentikasi otomatis jika `GITHUB_TOKEN` disetel di `.env`, dengan sanitasi masking token `***` pada log output agar kredensial aman dari kebocoran ke chat.
  - Menangani error `subprocess.CalledProcessError` dan exception sistem dengan aman.
- **`bot/handlers/commands.py` (`cmd_pull`)**:
  - Menggunakan off-thread worker `_async_to_thread` dengan timeout 30s.
  - Diselaraskan otentikasinya dengan `cmd_push` (`is_owner(uid) or role == ROLE_OWNER`).
- **`bot/handlers/commands.py` (`cmd_help_owner`)**:
  - Menambahkan baris dokumentasi `• /push [pesan]` pada kelompok **Pemeliharaan Server & Repositori**.
- **`bot/handlers/register.py`**:
  - Mendaftarkan handler `CommandHandler("push", commands.cmd_push)`.
- **`.gitignore`**:
  - Menambahkan `*.session*` dan `*.log` untuk mencegah file sesi Telegram dan log runtime ter-commit secara tidak sengaja saat `git add -A`.
- **`tests/test_help_and_export_json.py` (`test_cmd_push_and_cmd_pull`)**:
  - Menguji penolakan akses untuk non-owner pada `/pull` dan `/push`.
  - Menguji alur `/pull` sukses.
  - Menguji alur `/push` pada repositori bersih (clean repo).
  - Menguji alur `/push` pada repositori yang memiliki berkas berubah dengan pesan kustom (memverifikasi urutan `git status`, `git add -A`, `git commit -m`, dan `git push`).
- **`docs/commands.md` & `docs/architecture.md`**:
  - Menambahkan dokumentasi perintah `/push` dan alur sinkronisasi dua arah server.

## Verifikasi & QA
- `pytest tests/test_help_and_export_json.py tests/test_warkat.py tests/test_public_menu.py tests/test_mass_setrole_purna.py -v`: 21/21 PASSED (100%).
- `python tests/test_qa_master_audit.py`: 93/93 PASSED (100%).
