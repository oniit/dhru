# Aturan AI (Custom Agent Rules) untuk Proyek Ini

Dokumen ini berisi panduan dan instruksi _custom_ yang memengaruhi perilaku agen AI di Workspace ini.

## Aturan: Pembaruan Dokumentasi Otomatis (Auto-Update Docs)

**Deskripsi**: Agar dokumentasi _project_ tidak pernah usang dan selalu beriringan dengan versi kodenya, AI diwajibkan memperbarui direktori `docs/` dan `tasks/` pada kondisi tertentu.

**INSTRUKSI WAJIB BAGI AGEN AI:**
Setiap kali kamu menyelesaikan sebuah _task_ atau fitur pembaruan kode yang cukup signifikan (seperti fitur baru, refaktorisasi basis data, atau penutupan celah bug), **kamu harus melakukan dua hal ini SEBELUM mengakhiri sesimu dengan _user_**:
1. Cek isi direktori `docs/`. Jika perubahan kodemu mengubah arsitektur, menambah perintah (_command_), atau memodifikasi tabel database, kamu WAJIB mengedit `docs/architecture.md`, `docs/commands.md`, atau `docs/database.md` agar merefleksikan fitur terbarunya.
2. Cek direktori `tasks/`. Buatlah *file* markdown bernomor urut baru (misal: `003-new-feature.md`) yang merangkum apa saja yang baru kamu kerjakan, mengapa hal itu dikerjakan, dan bagaimana alur kodenya bekerja secara teknis.

Jangan pernah meninggalkan _workspace_ dalam keadaan fitur baru sudah selesai tapi tidak ada catatannya di `tasks/`. Selalu bertindak proaktif.
