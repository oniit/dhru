# Aturan AI (Custom Agent Rules) untuk Proyek Ini

Dokumen ini berisi panduan dan instruksi _custom_ yang memengaruhi perilaku agen AI di Workspace ini.

## Aturan: Pembaruan Dokumentasi Otomatis (Auto-Update Docs)

**Deskripsi**: Agar dokumentasi _project_ tidak pernah usang dan selalu beriringan dengan versi kodenya, AI diwajibkan memperbarui direktori `docs/` dan `tasks/` pada kondisi tertentu.

**INSTRUKSI WAJIB BAGI AGEN AI:**
Setiap kali kamu menyelesaikan sebuah _task_ atau fitur pembaruan kode yang cukup signifikan (seperti fitur baru, refaktorisasi basis data, atau penutupan celah bug), **kamu harus melakukan dua hal ini SEBELUM mengakhiri sesimu dengan _user_**:
1. Cek isi direktori `docs/`. Jika perubahan kodemu mengubah arsitektur, menambah perintah (_command_), atau memodifikasi tabel database, kamu WAJIB mengedit `docs/architecture.md`, `docs/commands.md`, atau `docs/database.md` agar merefleksikan fitur terbarunya.
2. Cek direktori `tasks/`. Buatlah *file* markdown bernomor urut baru (misal: `003-new-feature.md`) yang merangkum apa saja yang baru kamu kerjakan, mengapa hal itu dikerjakan, dan bagaimana alur kodenya bekerja secara teknis.

Jangan pernah meninggalkan _workspace_ dalam keadaan fitur baru sudah selesai tapi tidak ada catatannya di `tasks/`. Selalu bertindak proaktif.

## Aturan: Penggunaan Database (Turso)

**Deskripsi**: User secara eksklusif menggunakan Turso (remote database) alih-alih file SQLite lokal (`data/bot.db`).

**INSTRUKSI WAJIB BAGI AGEN AI:**
- Jangan pernah berasumsi bot berjalan dengan file `data/bot.db`.
- Selalu gunakan library `libsql_client` dan credentials di environment (`TURSO_DB_URL`, `TURSO_AUTH_TOKEN`) jika ingin melakukan eksekusi perintah ke database secara manual dari skrip Python.
- Jika ada file `data/bot.db`, HAPUS saja karena itu tidak digunakan.
- Saat melakukan inspeksi skema database, periksa struktur tabel dari `bot/database.py` (di mana DDL statis disimpan) atau query langsung ke Turso.

## Aturan: Proses Quality Assurance (QA)

**Deskripsi**: Panduan saat diminta melakukan QA (Quality Assurance) baik kecil maupun mendalam agar tidak mengganggu operasional pengguna asli bot.

**INSTRUKSI WAJIB BAGI AGEN AI:**
- **JANGAN PERNAH** mengirim pesan pengujian (test message), _broadcast_, pengumuman, atau notifikasi langsung ke sembarang _user_ atau grup saat sedang melakukan QA, baik menjalankan kode uji coba maupun melalui _endpoint_ notifikasi bot.
- Segala bentuk QA yang membutuhkan interaksi dengan bot harus dilakukan melalui akun khusus _tester_/_owner_ saja, menggunakan lingkungan replika (local mock), atau disimulasikan menggunakan skrip yang tidak benar-benar mengirim _request_ (send message) ke API Telegram untuk pengguna nyata. **Jika kamu sangat membutuhkan interaksi ke user nyata saat testing bot, maka kirimlah SATU-SATUNYA HANYA ke ID yang ada pada variabel `TESTER_ID` di dalam environment**.
- Evaluasi _logic_ harus mengandalkan skrip tes (misalnya menggunakan pytest / _local sqlite_ seperti `test_logic.py`) tanpa mengeksekusi fungsi _broadcast_/_send message_ ke _user_ yang ada di database *production*.
