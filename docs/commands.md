# Daftar Command & Fitur User Flow

Dokumen ini merangkum perintah yang dapat dipanggil (_command_) oleh pengguna dan alur utamanya.

## Manajemen Akun & Profil
- `/start` — Titik masuk utama. Membuat pengguna di DB jika belum ada.
- `/profil` — Menampilkan Kartu Profil pengguna (NIM, Jabatan, Poin Agra).
- `/lengkapi` — Memulai proses pengisian data (_onboarding_) yang belum lengkap.
- `/ubah` — Meminta perubahan data yang sudah terkunci (masuk ke antrean _pending_).

## Akademik & Kelas
- `/presensi` — (Bagi mahasiswa) Merekam kehadiran. (Bagi Dosen/Dekan) Menu membuka/menutup presensi.
- `/tugas` — Masuk ke _dashboard_ manajemen tugas (unggah tugas bagi dosen, kumpul tugas bagi mahasiswa).

## Sosial & Gamifikasi (Agra)
- `/leaderboard` — Menampilkan peringkat Agra mahasiswa teratas.
- `/transfer <jumlah> <@username>` — Mentransfer poin Agra ke pengguna lain.
- `/pay` — Mengurangi saldo Agra (opsional untuk pembayaran _virtual_).

## Manajemen (Khusus Owner / Admin / Staff Terpilih)
- `/setrole <role> <@username>` — Menetapkan peran (`admin`, `student`, dll) kepada pengguna.
- `/admin_data <username>` — Membuka menu pengeditan paksa terhadap profil pengguna (Bypass persetujuan).
- `/owner_reset` — (Hanya Owner) Menu sapu jagat untuk me-reset data presensi, log, atau _database_ secara massal.
- `/laporan` & `/daftar` — Mengekspor data rekapitulasi anggota ke dalam bentuk file atau _chat_.
- `/broadcast` — Mengirimkan pesan siaran ke semua saluran, bot _chats_, atau anggota fakultas tertentu.
- `/trigger` — Memanajemen daftar _auto-reply_ khusus berbasis kata kunci.
- `/pending` — Mengecek daftar ajuan perubahan profil pengguna.

## Ekstra
- `/ktm` & `/karpeg` — Menghasilkan gambar kartu ID Mahasiswa atau Pegawai berdasarkan _template_.
