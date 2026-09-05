# 059 - Export Photos Command

## Apa yang Dikerjakan
Menambahkan fitur bagi Owner/Admin untuk mengekspor semua data foto profil (KTM dan Karpeg) ke dalam satu buah file ZIP. 

## Mengapa Dikerjakan
- Permintaan langsung untuk mempermudah ekspor dan pendataan foto KTM dan Karpeg dalam satu *command*.
- Menggunakan satu file `.zip` agar lebih efisien (terhindar dari limit Telegram), tidak *spam* di riwayat chat admin, dan file diformat rapi per folder `KTM/` dan `Karpeg/`.

## Bagaimana Secara Teknis
1. Menambahkan fungsi `cmd_export_photos` di dalam `bot/handlers/commands.py`.
2. Fungsi berjalan secara asynchronous, memberikan laporan proses terlebih dahulu ke pengguna, melakukan query ke `users`, mengunduh file gambar (dari Telegram bot API menggunakan `download_as_bytearray()`), dan mengompres ke file `.zip` temporer.
3. Setelah dikumpulkan dan disimpan di `.zip`, file tersebut dikirim sebagai dokumen dengan _filename_ `Export_Photos.zip`.
4. File temporer dibersihkan dari sistem sesudahnya (`os.remove()`).
5. Memperbarui `bot/handlers/register.py` untuk me-register handler `export_photos`.
6. Memperbarui dokumentasi `docs/commands.md` sesuai AGENTS.md rule.
