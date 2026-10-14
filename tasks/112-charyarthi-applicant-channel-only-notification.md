# 112 - Pemisahan Notifikasi Pelamar (Channel) dan Lembar Jawaban Tes (Grup SDM)

## Ringkasan
Menghapus duplikasi kartu profil pelamar Chāryārthī beserta tombol keputusan (*Accept/Reject*) ke grup Tim SDM (`SDM_GID`), sehingga:
1. **Kartu Pelamar & Tombol Keputusan**: Terpusat satu pintu dikirim hanya ke Channel Pendaftar (`PENDAFTAR_CH_ID`).
2. **Lembar Jawaban Soal Tes Divisi**: Tetap dikirim ke Grup Tim SDM (`SDM_GID`) untuk ditinjau dan diperiksa oleh tim SDM secara terstruktur.

## Alasan
Sebelumnya, ketika pelamar menekan tombol submit pendaftaran, kartu pendaftar dengan tombol keputusan (*Accept/Reject*) dikirim ke dua tempat (Channel Pendaftar dan Grup SDM). Ini membingungkan reviewer dan rentan konflik keputusan jika tombol ditekan di dua tempat berbeda. Dengan pemisahan ini, keputusan kelulusan dipusatkan di Channel Pendaftar, sementara grup SDM fokus menerima lembar jawaban tes divisi pelamar.

## Perubahan Teknis
- **`bot/handlers/commands.py` (`action == "submit"`)**:
  - `PENDAFTAR_CH_ID`: Menerima pesan rekap pelamar (`msg_admin`) lengkap dengan `InlineKeyboardMarkup(admin_buttons)`.
  - `SDM_GID`: Menerima header lembar jawaban `LEMBAR JAWABAN TES DIVISI (TIM SDM)` beserta pesan bersambung jawaban esai pelamar (tanpa tombol keputusan pendaftaran). Jika divisi tidak memiliki soal tes, grup SDM tidak dikirimi pesan kosong.
- **`tests/test_charyarthi.py`**:
  - Memperbarui pengujian integrasi callback `charyarthi:submit` untuk memastikan `PENDAFTAR_CH_ID` menerima `reply_markup` tombol keputusan, sedangkan `SDM_GID` menerima lembar jawaban tanpa tombol keputusan (`reply_markup is None`).

