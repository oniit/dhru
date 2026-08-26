# Task 013: Penyesuaian Terminologi Role Lokal (Pravesin, Sisya, Charya, Publik)

**Deskripsi Singkat:**
Menyesuaikan nama panggilan/kategori untuk _role_ pada command `/tagall` (termasuk `/all`), `/daftar`, dan `/agra top` agar menggunakan istilah lokal yang lebih menyatu dengan _lore_ komunitas.

**Perubahan yang Dilakukan:**
1. **Mapping Terminologi**:
   - `publik` = Publik/Eksternal
   - `pravesin` = Mahasiswa Baru (MABA)
   - `sisya` = Mahasiswa Aktif & BEM
   - `charya` = Staf Internal, Admin, Owner
2. **`bot/handlers/commands.py` (Command `/all` / `/tagall`)**:
   - Menambahkan opsi parameter filter langsung seperti: `/tagall sisya`, `/tagall pravesin`, `/tagall charya`, `/tagall publik`.
   - Modifikasi `cmd_all` agar mengurai (_parse_) filter tersebut dan mencocokkannya ke database (contoh `sisya` otomatis mencakup _role_ `student` dan `bem`).
3. **`bot/handlers/commands.py` (Command `/daftar`)**:
   - Menghapus sub-command usang `/daftar mhs`, `/daftar admin`, `/daftar staf`, dan `/daftar all_staf`.
   - Menggantinya dengan `/daftar sisya`, `/daftar charya`, `/daftar pravesin`, `/daftar publik` yang otomatis mengelompokkan data secara rapi.
4. **`bot/handlers/commands.py` (Command `/agra`)**:
   - Memperbarui papan peringkat `/agra top` agar nama tampilannya berubah menjadi _(Pravesin)_, _(Sisya)_, _(Charya)_, dan _(Publik)_.
   - Mengganti pemanggilan lama `/agra top ext` menjadi `/agra top publik`.
   - Menambahkan _board_ `/agra top pravesin`.
   - Menyesuaikan teks menu bantuan saat `/agra` dipanggil tanpa argumen.

**Status:** Selesai.
