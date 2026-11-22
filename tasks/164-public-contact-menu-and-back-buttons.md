# Task 164: Pembaruan Menu Hubungi Instansi Publik & Penambahan Tombol Kembali

## 1. Deskripsi & Latar Belakang
User meminta penyesuaian pada menu interaktif publik saat memilih opsi "📞 Hubungi Instansi":
1. Mengubah username kontak kemitraan (medpart) menjadi `@dhruvamitrabot`.
2. Menambahkan menu baru di paling atas pada daftar pilihan instansi: `"Kirim undangan acara."` yang mengarahkan ke `@dhruvaekagrabot`.
3. Menambahkan tombol navigasi `"⬅️ Kembali"` pada seluruh sub-menu instansi dan menu interaktif publik lainnya agar pengguna dapat dengan mudah berpindah kembali tanpa harus mengetik manual `/start`.

## 2. Rincian Perubahan Teknis
### A. Handler Callback Publik (`bot/handlers/commands.py`)
- **Menu Pilihan Instansi (`pub:hubungi`)**:
  - Tombol paling atas: `[InlineKeyboardButton("Kirim undangan acara.", callback_data="pub:undangan")]`.
  - Tombol kedua: `[InlineKeyboardButton("Seputar kemitraan dan sejenisnya.", callback_data="pub:medpart")]`.
  - Tombol ketiga: `[InlineKeyboardButton("Menghubungi staf SDM.", callback_data="pub:hrd")]`.
  - Tombol keempat: `[InlineKeyboardButton("Menghubungi staf Akademik.", callback_data="pub:akademik")]`.
  - Tombol penutup: `[InlineKeyboardButton("⬅️ Kembali", callback_data="pub:back")]`.
- **Rincian Kontak Instansi (`pub:undangan`, `pub:medpart`, `pub:hrd`, `pub:akademik`)**:
  - Mengarahkan `undangan` ke `@dhruvaekagrabot`.
  - Mengarahkan `medpart` ke `@dhruvamitrabot`.
  - Mengarahkan `hrd` ke `@HRDhruvabot`.
  - Mengarahkan `akademik` ke `@acadhruvabot`.
  - Menambahkan inline keyboard `[InlineKeyboardButton("⬅️ Kembali", callback_data="pub:hubungi")]` pada seluruh pesan kontak instansi.
- **Menu Pertanyaan Lainnya (`pub:lainnya`)**:
  - Menambahkan inline keyboard `[InlineKeyboardButton("⬅️ Kembali", callback_data="pub:back")]`.
- **Menu Masukkan Kode Akademik (`pub:kode`)**:
  - Menambahkan inline keyboard `[InlineKeyboardButton("⬅️ Kembali", callback_data="pub:back")]`.
- **Aksi Kembali (`pub:back`)**:
  - Secara otomatis membersihkan state `INPUT_CODE` jika pengguna membatalkan/kembali dari menu input kode.
  - Me-render ulang menu utama pengguna publik.

### B. Dokumentasi & Pengujian (`docs/` & `tests/`)
- **`docs/commands.md`**: Diperbarui pada deskripsi `/start` publik untuk mencantumkan rincian kontak instansi dan navigasi tombol kembali.
- **`tests/test_public_menu.py`**: Dibuat tes suite otomatis untuk memvalidasi:
  - Urutan tombol pada `pub:hubungi`.
  - Kontak username yang benar untuk `pub:undangan` (`@dhruvaekagrabot`) dan `pub:medpart` (`@dhruvamitrabot`).
  - Keberadaan tombol kembali pada setiap respon sub-menu.
  - Pembersihan state `INPUT_CODE` saat menekan tombol kembali ke menu utama.

## 3. Hasil Verifikasi
- `pytest tests/test_public_menu.py tests/test_warkat.py tests/test_mass_setrole_purna.py tests/test_help_and_export_json.py -v`: 19 passed.
- `python tests/test_qa_master_audit.py`: 93 passed, 0 failed.
