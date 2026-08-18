# Fix Maba Verification Bug

**Task**: Fix a bug where the Maba (Mahasiswa Baru) registration gets stuck when verifying channels ("gada respon, checklistnya tetap seperti verifikasi pertama, lalu udh join semua tp gak ada respon jg stuck di verifikasi").

## Akar Masalah
1. **Pesan Tidak Berubah (BadRequest)**: Jika *user* menekan tombol "Verifikasi Kembali" namun status *follow/join* *channel*-nya belum bertambah, bot akan menghasilkan teks (pesan) yang *identik* 100% dengan teks yang sedang ditampilkan. Ketika `edit_message_text` dipanggil dengan teks yang persis sama, Telegram API memunculkan `BadRequest: Message is not modified`. Karena ini tidak ditangkap (`try-except`), eksekusi *callback* langsung berhenti di tengah jalan. Hal ini mengakibatkan tombol hanya "berputar-putar" tanpa ada balasan apa pun (*gada respon*).
2. **Pemanggilan Method Database Salah**: Ketika *user* akhirnya berhasil bergabung di semua *channel* yang diwajibkan (`all_followed = True`), *script* memanggil fungsi `await db.update_user_role(conn, uid, ROLE_MABA)`. Sayangnya, fungsi `update_user_role` **tidak ada** di `bot/database.py`, fungsi yang benar adalah `set_role`. Kesalahan nama *method* ini memunculkan `AttributeError` dan kembali menghentikan eksekusi, sehingga *user* tetap tersangkut di langkah verifikasi tanpa adanya konfirmasi sukses atau pergantian *role*.

## Penyelesaian (Solusi Teknis)
1. **Penambahan Timestamp**: Di `bot/handlers/common.py` (pada fungsi `build_maba_verification_text`), saya menambahkan keterangan waktu (contoh: `_(Terakhir dicek: 14:43:10)_`) di bagian paling bawah teks verifikasi. Ini menjamin setiap kali tombol "Verifikasi Kembali" ditekan, teks balasan selalu unik (waktunya berbeda sedetik/semenit), sehingga menghindarkan *bot* dari `BadRequest: Message is not modified`.
2. **Perbaikan Nama Method**: Di `bot/handlers/commands.py` (pada bagian aksi `maba:verify`), saya mengganti pemanggilan `db.update_user_role` menjadi `db.set_role` agar proses pengangkatan status menjadi `maba` dapat dieksekusi dengan benar tanpa menabrak `AttributeError`.

Bug ini kini telah teratasi sehingga proses verifikasi *channel* akan berjalan mulus, dan *user* maba baru bisa sukses terdaftar.
