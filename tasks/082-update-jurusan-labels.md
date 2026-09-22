# 082 — Update UI/UX Penamaan Jurusan

## Deskripsi
Sesuai permintaan, penyebutan nama jurusan pada antarmuka (terutama command `/daftar` dan profil pengguna) telah disederhanakan dan dibersihkan dari ID mentah:

- **ik** menjadi **Kimia**
- **if** menjadi **Fisika**
- **sm** menjadi **Musik**
- **sf** menjadi **Fotografi**

## Perubahan Kode
1. **`config/choices.yaml`**: Mengubah nilai `label` pada `majors` dari versi lengkap/resmi ("Ilmu Kimia") menjadi versi singkat ("Kimia") agar UI/UX lebih rapi saat user mengisi profil atau melihat profil pengguna.
2. **`bot/handlers/commands.py`**:
   - Memodifikasi `cmd_daftar` agar meng-import fungsi `choice_label` dari `bot.settings`.
   - Menambahkan mapping nama (dari ID ke Label) pada teks menu panduan `/daftar`. Misalnya: `/daftar jurusan <id> — ik (Kimia), if (Fisika), ...`.
   - Memperbarui title hasil balasan command dari misalnya "Daftar — jurusan ik" menjadi "Daftar — Jurusan Kimia" dan "Daftar — Kelas Fisika Dasar".

## Status
Perubahan selesai diterapkan dan langsung berlaku. Saat memanggil `/daftar jurusan ik`, balasan pesan bot sekarang memiliki judul `Daftar — Jurusan Kimia` (tidak lagi menggunakan ID mentah).
