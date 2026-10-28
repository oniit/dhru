# Task 129: Pembaruan Label Jabatan Wakil Rektor Menjadi Biro di Pilihan Konfigurasi

## Ringkasan Perubahan
Menyesuaikan nama tampilan (`label`) untuk jabatan Wakil Rektor (Pratinidhi) agar merefleksikan pembagian biro pada kampus Dhruva tanpa mengubah `id` teknis di basis data.

1. **Perubahan pada `positions` (`config/choices.yaml`)**:
   - `warek1`: `Pratinidhi I प्रतिनिधि I` -> `Pratinidhi प्रतिनिधि`
   - `warek2`: `Pratinidhi II प्रतिनिधि II` -> `Pratinidhi प्रतिनिधि`
   - `warek3`: `Pratinidhi III प्रतिनिधि III` -> `Pratinidhi प्रतिनिधि`
   - Menghapus penomoran romawi (I, II, III) sehingga seragam menjadi gelar `Pratinidhi प्रतिनिधि`.

2. **Perubahan pada `position_details` (`config/choices.yaml`)**:
   - `d_warek1`: `Wakil Rektor I` -> `Biro Akademik`
   - `d_warek2`: `Wakil Rektor II` -> `Biro Umum`
   - `d_warek3`: `Wakil Rektor III` -> `Biro Eksternal`

## Pertimbangan Teknis & Dampak
- **Zero Database Migration**: `id` tetap dipertahankan (`warek1`, `warek2`, `warek3`, `d_warek1`, `d_warek2`, `d_warek3`) sehingga akun pimpinan atau data pengguna eksisting di database remote Turso tetap 100% kompatibel dan tidak mengalami kerusakan tampilan kartu identitas (`/kic`).
- **Pengecualian Calon Staf Aman**: Fungsi `get_charyarthi_divisions()` di `bot/settings.py` yang mengecualikan `d_warek1`, `d_warek2`, dan `d_warek3` dari pendaftaran calon staf tetap bekerja sebagaimana mestinya tanpa ada kebocoran divisi pimpinan.
