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
- `/menfess` — Membuka menu pengiriman pesan rahasia (menfess) ke pengguna lain dengan biaya Agra, serta melihat history.
- `/menfess_read <id>` — Membaca detail pesan menfess dari history.
- `/link_kerja` — Membuat kode OTP untuk menautkan "Akun Kerja" (akun promosi).
- `/cek_akun_kerja` — Melihat daftar akun kerja yang sudah ditautkan.
- `/lpm <link>` — Men-submit link pesan promosi dari grup publik untuk divalidasi dan mendapatkan reward Agra.
- `/story <link>` — Men-submit link Story Telegram yang berisi repost _channel post_ untuk divalidasi dan mendapatkan reward Agra.

## Manajemen (Khusus Owner / Admin / Staff Terpilih)
- `/promo` — (Hanya Owner) Membuka menu pengaturan Syarat Kata LPM dan Link target Story secara dinamis.
- `/setrole <role> <@username>` — Menetapkan peran (`admin`, `student`, dll) kepada pengguna.
- `/add <role/@username> <jumlah> | <deskripsi>` — Menambahkan/mengurangi Agra secara spesifik ke pengguna atau grup role (contoh: `/add internal 50`).
- `/admin_data <username>` — Membuka menu pengeditan paksa terhadap profil pengguna (Bypass persetujuan).
- `/owner_reset` — (Hanya Owner) Menu sapu jagat untuk me-reset data presensi, log, atau _database_ secara massal.
- `/reload` — (Hanya Owner/Admin) Memulai ulang layanan bot secara langsung lewat terminal (`sudo systemctl restart botdhru`).
- `/laporan` & `/daftar` — Mengekspor data rekapitulasi anggota ke dalam bentuk file atau _chat_.
- `/detail` — Sama seperti `/daftar` namun menyertakan data Tanggal Lahir dan Muse, diurutkan berdasarkan hari ulang tahun terdekat.
- `/broadcast` — Mengirimkan pesan siaran ke semua saluran, bot _chats_, atau anggota fakultas tertentu.
- `/trigger` — Memanajemen daftar _auto-reply_ khusus berbasis kata kunci.
- `/pending` — Mengecek daftar ajuan perubahan profil pengguna.

## Ekstra
- `/ktm` & `/karpeg` — Menghasilkan gambar kartu ID Mahasiswa atau Pegawai berdasarkan _template_.

## Mini Games
- `/bermain` — Menampilkan daftar mini-games yang tersedia.
- `/bermain <game_name> <args>` — Memulai sesi game di grup.
  - *Kata Rahasia:* `/bermain kata_rahasia <setting>`
  - *Kantong Rempah:* `/bermain kantong_rempah [menit_setor] [menit_tebak]`
  - *Tahan Dulu:* `/bermain tahan_dulu [detik]`
  - *Adu React:* `/bermain adu_react`
- `/tebak <angka>` — (Khusus Game) Menebak angka saat fase tebak berlangsung (contoh: Kantong Rempah).
- `/status <game_name>` — Mengecek status dan skor sementara game yang sedang berjalan.
- `/berhenti <game_name>` — (Admin/Pemulai) Menghentikan game dan menampilkan skor akhir.
- `/hasil <game_name>` — Menampilkan skor akhir dari sesi game terakhir jika tertinggal.
