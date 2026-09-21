# 080 - Fix Data Command

## Apa yang Dikerjakan
Menambahkan command Telegram `/fix` khusus untuk Owner dan Admin. Command ini akan menjalankan *script* validasi massal dan rekapitulasi ulang (sebelumnya `fix_data.py`) secara langsung dari bot tanpa harus menjalankannya lewat terminal server.

## Mengapa Dikerjakan
User meminta agar proses validasi dan perhitungan ulang *Total SKS* secara massal bisa dilakukan lebih mudah lewat Telegram, terutama setelah ada perubahan *properties* (misal: major, id) pada `choices.yaml` yang tidak bisa ditarik secara dinamis pada JSON `profile_json` yang sudah tersimpan statis.

## Alur Kode Secara Teknis
1. Di `commands.py`, dibuat sebuah asinkron `cmd_fix_data` yang dilindungi *role checking* (`ROLE_OWNER` & `ROLE_ADMIN`).
2. Fungsi ini menarik *query* `SELECT telegram_id, role, profile_json FROM users`.
3. Ia melakukan *looping* ke semua *row* yang didapatkan, kemudian mengeksekusi `await db.set_profile_partial(conn, uid, prof)` untuk setiap *user*.
4. Di *background*, `set_profile_partial` secara otomatis memanggil `_apply_generated_profile_fields` yang membersihkan kunci invalid dan merekap kembali angka *Total SKS*.
5. *Command* ini mengirimkan pesan `⏳ Sedang memvalidasi...` di awal dan di-edit menjadi `✅ Berhasil memvalidasi...` di akhir untuk UX yang interaktif.
6. Diregistrasikan di `register.py` ke dalam `CommandHandler("fix", commands.cmd_fix_data)`.
7. Didokumentasikan di `docs/commands.md`.
