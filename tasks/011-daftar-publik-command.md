# Task 011: Perbaikan Bug Inline Keyboard dan Penambahan Command Publik

**Deskripsi Singkat:**
Menambahkan perbaikan (bugfix) terhadap isu _Message is not modified_ pada callback query, serta menambahkan perintah khusus untuk pendaftaran ulang publik lama menjadi MABA.

**Alasan Pengerjaan:**
- Dilaporkan bahwa akun baru terkadang tidak merespons (gak bisa klik) saat menekan tombol "Daftar Akun Publik".
- Saat berada di menu "Hubungi Instansi", menekan tombol "Kembali" juga di-laporkan tidak berfungsi.
- Pengguna publik lama yang ingin mendaftar sebagai MABA (tanpa paksaan /setrole admin) tidak bisa melihat tombol MABA karena datanya sudah terisi (sudah pernah melengkapi), sehingga butuh command spesifik.

**Implementasi:**
1. **`bot/handlers/commands.py`**:
   - Menambahkan blok `try...except` pada pemanggilan `q.edit_message_text` di beberapa tempat kunci: saat membatalkan aksi (`cancel_action`), menangani menu instansi (`pub:hubungi`), menangani kembalinya menu utama (`pub:back`), dan pemicu registrasi publik (`openlt:`).
   - Penanganan _exception_ ini memastikan jika Telegram melempar *error* `telegram.error.BadRequest: Message is not modified` (biasa terjadi karena limitasi update teks pada cache), alur kode tidak akan macet (nge-hang) dan tetap berlanjut memproses instruksi.
   - Menambahkan fungsi perintah baru: `cmd_maba`. Ini akan menyetel `onboarding_step` menjadi `MABA_NAME` secara langsung tanpa harus menekan tombol `maba:start` (yang tidak akan muncul untuk pengguna lama).
2. **`bot/handlers/register.py`**:
   - Mendaftarkan perintah (command) baru: `/maba`.
3. **`docs/commands.md`**:
   - Memperbarui dokumentasi terkait rincian daftar *command* baru yang dibuat.
