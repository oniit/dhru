# Task 114: Deep QA Bug Fixes (/daftar, /agratop, /export_photos)

## Latar Belakang & Masalah
Dalam proses evaluasi QA mendalam sistem terhadap basis kode [qa.md](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/docs/qa.md), ditemukan 3 kelemahan/bug logika fungsional:
1. **Orphaned String / Dead Menu:** String `<code>/daftar all_staf</code>` tertera di pesan menu bantuan `/daftar` sebagai sisa refaktorisasi Task 013 (di mana `all_staf` telah digantikan oleh `charya`). Hal ini membuat menu tampak memiliki perintah yang tidak berfungsi.
2. **Missing Role Filter:** Role alumni `ROLE_PURVA` (`purva`) tidak didukung pada `/agratop purva` maupun `/daftar purva`. Pengguna alumni yang memiliki poin Agra tidak bisa difilter di leaderboard.
3. **Resource Leak Risk:** Pada `/export_photos`, pembuatan file arsip sementara via `tempfile.NamedTemporaryFile` hanya menghapus file zip di jalur sukses. Jika terjadi exception di tengah kompresi/pengiriman, file zip tidak terhapus dan mengotori disk server.

## Perubahan yang Dilakukan
1. **`bot/handlers/commands.py`**:
   - Menghapus teks sisa `<code>/daftar all_staf</code>` dari menu bantuan `/daftar`, menegaskan standar komunitas resmi `/daftar charya` (Staf Internal, Admin, Owner).
   - Menambahkan penanganan `kind == "purva"` di `cmd_daftar` untuk menampilkan daftar alumni (`ROLE_PURVA`).
   - Menambahkan opsi `sub == "purva"` di `cmd_agratop` untuk memfilter leaderboard Agra khusus pengguna berstatus alumni/purva.
   - Menambahkan menu petunjuk `<code>/daftar purva</code>` pada respons bantuan `/daftar`.
   - Membungkus proses pembuatan arsip zip pada `cmd_export_photos` ke dalam blok `try...finally` agar file temporary zip selalu dihapus (`os.remove`) meskipun terjadi error.
2. **`tests/test_qa_fixes.py`**:
   - Menambahkan automated integration test komprehensif menggunakan Turso DB untuk memverifikasi eksekusi `/daftar charya`, `/daftar purva`, `/agratop purva`, dan memastikan teks `all_staf` bersih dari menu `/daftar`.
3. **Dokumentasi**:
   - Memperbarui `docs/commands.md` dengan deskripsi parameter terbaru `/daftar`.
