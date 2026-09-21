# Chained Major Selection

**Tujuan:**
Mengubah alur pemilihan Jurusan dan Fakultas agar menjadi satu kesatuan (berurutan) melalui satu tombol `Jurusan` di menu `/lengkapi` dan `/ubah`, sesuai permintaan user. 

**Perubahan yang Dilakukan:**
1. **Sembunyikan Tombol Fakultas di Menu Utama**: Mengubah role akses pada field `faculty` di `config/profile_fields.yaml` menjadi `['_hidden']` sehingga tidak muncul lagi sebagai opsi yang mandiri di menu `/lengkapi`.
2. **Pertahankan Fakultas di Profil**: Menyesuaikan `bot/handlers/common.py` pada fungsi `display_keys_for_role` agar field `faculty` tetap dirender pada kartu profil mahasiswa walaupun memiliki role `_hidden`.
3. **Chain Callback `/lengkapi`**: Memodifikasi `openlc:major` di `bot/handlers/commands.py` untuk mengarahkan pengguna memilih Fakultas terlebih dahulu (`lc_fac_for_maj:`), lalu secara otomatis dialihkan ke menu Jurusan (`lc:major`).
4. **Chain Callback `/ubah`**: Memodifikasi alur `openec:major` untuk menyimpan pilihan fakultas sementara di memori (`temp_ec_faculty`), lalu mengirimkannya bersamaan saat user menyelesaikan pilihan jurusannya untuk disetujui Admin.

**Alur Baru**:
- User ketik `/lengkapi`.
- Tersedia opsi `✏️ Jurusan` (opsi Fakultas tidak ada).
- User klik `✏️ Jurusan`.
- Bot memunculkan menu `Pilih Fakultas terlebih dahulu:`.
- User pilih Fakultas.
- Bot memunculkan menu `Pilih Jurusan:`.
- User pilih Jurusan -> Fakultas dan Jurusan tersimpan.
