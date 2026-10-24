# Daftar Command & Fitur User Flow

Dokumen ini merangkum perintah yang dapat dipanggil (_command_) oleh pengguna dan alur utamanya.

## Manajemen Akun & Profil
- `/start` — Titik masuk utama. Membuat pengguna di DB jika belum ada.
- `/profil` — Menampilkan Kartu Profil pengguna (NIM, Jabatan, Poin Agra).
- `/lengkapi` — Memulai proses pengisian data (_onboarding_) yang belum lengkap.
- `/ubah` — Meminta perubahan data yang sudah terkunci (masuk ke antrean _pending_).
- `/maba` — Command untuk mendaftar sebagai Mahasiswa Baru (terutama bagi user publik yang datanya sudah terisi).
- `/charyarthi` — Memulai formulir pendaftaran calon staf (Chāryārthī) secara interaktif.
- `/cancel` atau `/batal` — Membatalkan proses pengisian data atau interaksi aktif dan kembali ke kondisi awal.

## Akademik & Kelas
- `/presensi` — Merekam kehadiran. Menu membuka/menutup presensi untuk jenis sesi tertentu (Mata Kuliah, Charya, Yaksa/BEM, dan Umum; sesi manual otomatis ditutup setelah 2 jam). Pembina BEM (Āchāryata) memiliki hak akses membuka, menghadiri, dan merekap Presensi Yaksa. Penutupan sesi Presensi Umum dibatasi ketat hanya untuk pembuat sesi atau Admin/Owner.
- `/tugas` — Masuk ke _dashboard_ manajemen tugas (unggah tugas bagi dosen, kumpul tugas bagi shishya).

## Sosial & Gamifikasi (Agra)
- `/leaderboard` atau `/agra top [role] [all]` — Menampilkan peringkat Agra teratas. Gunakan argumen `all` untuk melihat keseluruhan tanpa batas Top 17 (contoh: `/agra top charya all`).
- `/transfer <jumlah> <@username>` atau `/pay <jumlah> <@username>` — Mentransfer poin Agra ke pengguna lain.
- `/menfess` — Membuka menu pengiriman pesan rahasia (menfess) ke pengguna lain dengan biaya Agra, serta melihat history.
- `/menfess_read <id>` — Membaca detail pesan menfess dari history.
- `/manosraya` — Mengirim aspirasi, kritik, atau saran anonim (Yaksa Open Arms) ke sistem/Dhruva. Tanpa biaya Agra (Tersedia Senin-Jumat, 10.00-22.00 WIB).
- `/link_kerja` — Membuat kode OTP untuk menautkan "Akun Kerja" (akun promosi).
- `/cek_akun_kerja` — Melihat daftar akun kerja yang sudah ditautkan.
- `/lpm <link>` — Men-submit link pesan promosi dari grup publik untuk divalidasi dan mendapatkan reward Agra.
- `/story <link>` — Men-submit link Story Telegram yang berisi repost _channel post_ untuk divalidasi dan mendapatkan reward Agra.

## Manajemen (Khusus Owner / Admin / Staff Terpilih)
- `/chat <@username|ID> <pesan>` — (Hanya Owner) Mengirim pesan atau media secara langsung & polos ke private chat user dari bot. Mendukung lampiran media langsung (caption) atau me-reply media apa pun.
- `/promo` — (Hanya Owner) Membuka menu pengaturan Syarat Kata LPM dan Link target Story secara dinamis.
- `/setrole <role> <@username>` — Menetapkan peran (`admin`, `student`, dll) kepada pengguna.
- `/kick <@username|ID>` — (Owner/Admin/Sekre) Mengeluarkan target dari grup. Jika dijalankan di dalam grup, langsung mengeluarkan anggota dari grup tersebut. Jika dijalankan via PM (private chat bot), bot akan secara dinamis mengecek keanggotaan target dan hanya menampilkan daftar tombol grup di mana target tersebut benar-benar bergabung.
- `/kicknot <role1> <role2>...` — (Hanya Owner/Admin di Grup) Mengeluarkan (_mass-kick_) semua anggota di grup yang TIDAK memiliki role yang disebutkan.
- `/add <role/@username> <jumlah> | <deskripsi>` — Menambahkan/mengurangi Agra secara spesifik ke pengguna atau grup role (contoh: `/add internal 50`).
- `/admin_data <username>` — Membuka menu pengeditan paksa terhadap profil pengguna (Bypass persetujuan).
- `/pindah_data <id_lama|@username_lama> <id_baru|@username_baru>` — (Khusus Owner) Memindahkan seluruh data profil, peran/role, saldo Agra, riwayat presensi, tugas, dll dari akun lama ke akun baru.
- `/orreset_user <id> <tipe>`: (Owner) Reset data profil user (onboarding, rank, dll).
- `/orreset_agra <id> <tipe>`: (Owner) Reset balance/history Agra user.
- `/reload`: (Owner/Admin) Memuat ulang module dinamis, config, dll tanpa me-restart server secara penuh.
- `/pull`: (Owner/Admin) Menarik pembaruan kode terbaru dari repositori menggunakan perintah `git pull` dan menampilkan log perubahannya.
- `/ospek_mode [on|off]`: (Owner/Admin) Menghidupkan atau mematikan fitur otomatis kegiatan Ospek Maba (misalnya rutinitas presensi harian otomatis untuk Maba jam 15:00-22:00).
- `/laporan` & `/daftar` — Mengekspor data rekapitulasi anggota ke dalam bentuk file atau _chat_ (mendukung filter `shishya`, `charya`, `charyarthi`, `pravesi`, `purva`, `publik`, serta filter fakultas, jurusan, kelas, dan ukm). Menyesuaikan otomatis dengan wewenang Dosen/Dekan dan menyertakan staf pada filter fakultas/jurusan.
- `/detail` — Sama seperti `/daftar` namun menyertakan data Tanggal Lahir dan Muse, diurutkan berdasarkan hari ulang tahun terdekat.
- `/all [role|fakultas|jurusan|ukm|kelas|kelompok <val>]` — (Admin/Staf) Mention massal (_tagall_) anggota grup sesuai filter yang ditentukan.
- `/acc_charyarthi <user_id> [1|2]` — (Owner/Admin) Menerima pelamar Chāryārthī menjadi staf internal pada divisi pilihan 1 atau 2, dan mengirimkan notifikasi instruksi tanda tangan `/kontrak`.
- `/reject_charyarthi <user_id>` — (Owner/Admin) Menolak pelamar Chāryārthī, me-rollback role ke `public`, dan mengirimkan pesan apresiasi sopan.
- `/setting_charyarthi` — (Owner/Admin) Menu interaktif tombol toggle (✅/❌) saklar pendaftaran Chāryārthī master switch dan per divisi yang dibuka.
- `/soal [divisi]` / `/soal_divisi` — (Owner/Admin/SDM/Staf Internal) Menu interaktif pemilihan divisi dan pengelolaan soal tes studi kasus calon staf Chāryārthī. ID divisi yang tersedia: `dekan`, `guru_besar`, `dosen`, `coach`, `pembina`, `editor`, `hrd`, `sarpras`, `mpps`, `pfp`, `pr`.
- `/setsoal <divisi>\n1. Soal 1\n2. Soal 2...` — (Owner/Admin/SDM/Staf Internal) Mengatur seluruh daftar soal divisi sekaligus secara cepat via copy-paste.
- `/tambah_soal <divisi> <pertanyaan>` — (Owner/Admin/SDM/Staf Internal) Menambahkan 1 soal baru pada urutan terakhir divisi.
- `/hapus_soal <divisi> <no_soal>` — (Owner/Admin/SDM/Staf Internal) Menghapus soal pada nomor urut tertentu dan mengurutkan ulang sisanya.
- `/reset_soal <divisi>` — (Owner/Admin/SDM/Staf Internal) Mengosongkan seluruh soal tes untuk divisi tersebut.
- `/broadcast` — Mengirimkan pesan siaran ke semua saluran, bot _chats_, atau anggota fakultas tertentu.
- `/trigger` — Memanajemen daftar _auto-reply_ khusus berbasis kata kunci.
- `/pending` — Mengecek daftar ajuan perubahan profil pengguna.
- `/setgreeting [pesan|off]` — (Owner/Admin) Mengatur pesan sambutan khusus grup. Mendukung placeholder `{name}` dan `{username}`.
- `/greeting` — Menampilkan pesan sambutan yang sedang aktif di grup.
- `/export_photos` — (Owner/Admin) Mengekspor semua data foto KTS dan KIC dalam satu file `.zip`.
- `/fix` — (Owner/Admin) Menjalankan validasi massal dan rekapitulasi ulang terhadap semua data profil *user* di *database* secara asinkron.

## Ekstra
- `/kartu` & `/foto` — Menghasilkan gambar kartu ID (KTS/KIC) otomatis berdasarkan peran pengguna, dan mengatur pas foto kartu.
- `/kontrak` — Manajemen kontrak kerja staf internal:
  - `/kontrak saya` — Meninjau draf (staf baru) atau melihat kontrak kerja aktif staf.
  - `/kontrak ttd` — Mengunggah foto tanda tangan digital baru.
  - `/kontrak sahkan` — Mengesahkan dan menerbitkan draf kontrak kerja staf baru.
  - `/kontrak renew` — Memperbarui kontrak kerja untuk periode berikutnya (tersedia mulai H-7 sebelum masa kontrak berakhir atau jika telah kedaluwarsa).
  - `/kontrak all` — (Admin/Owner) Menampilkan daftar semua staf internal beserta status kontrak, nomor ID, termin ke-N, dan tanggal bergabung.
  - `/kontrak check <@username/id>` — (Admin/Owner) Melihat gambar kontrak dan rincian teks riwayat lengkap penandatanganan kontrak staf.

## Mini Games
- `/settings_game` — (Owner/Admin Grup) Membuka menu interaktif untuk mengaktifkan/menonaktifkan game tertentu di grup ini. Game yang dinonaktifkan tidak dapat dimainkan.
- `/atur <game_name> <setting_name> <args>` — Mengatur konfigurasi game (Create/Update).
- `/hapus_setting <game_name> <setting_name>` — Menghapus konfigurasi game.
- `/cek_setting <game_name>` — Menampilkan daftar konfigurasi game yang sudah diatur.
- `/bermain` — Menampilkan daftar mini-games yang tersedia.
- `/bermain <game_name> <args>` — Memulai sesi game di grup.
  - *Kata Rahasia:* `/bermain kata_rahasia <setting>`
  - *Kantong Rempah:* `/bermain kantong_rempah [menit_setor] [menit_tebak]`
  - *Tahan Dulu:* `/bermain tahan_dulu [nama_setting] [delay_detik]`
  - *Adu React:* `/bermain adu_react`
  - *Tujuh Pusaka:* `/bermain tujuh_pusaka`
  - *Ketik Angka:* `/bermain ketik_angka [max_pemenang]`
- `/tebak <angka>` — (Khusus Game) Menebak angka saat fase tebak berlangsung (contoh: Kantong Rempah).
- `/ikut` — Bergabung ke dalam game (contoh: Tujuh Pusaka).
- `/mulai_game` — (Admin/Pemulai) Memulai ronde 1 pada game (contoh: Tujuh Pusaka).
- `/pusaka <kartu>` — (Khusus Game Tujuh Pusaka) Memilih kartu pusaka yang akan dikeluarkan.
- `/status <game_name>` — Mengecek status dan skor sementara game yang sedang berjalan.
- `/berhenti <game_name>` — (Admin/Pemulai) Menghentikan game dan menampilkan skor akhir.
- `/hasil <game_name>` — Menampilkan skor akhir dari sesi game terakhir jika tertinggal.

## Promosi & Verifikasi
- `/lpm <link>` — Mengirimkan link pesan promosi di grup publik untuk divalidasi sistem (memberikan reward +1 Agra jika valid).
- `/story <link>` — Mengirimkan link bukti repost Story Telegram untuk divalidasi.
- `/link_kerja` — Menghasilkan kode OTP untuk menautkan akun cadangan (Akun Kerja) ke akun utama.
- `/cek_akun_kerja` — Melihat daftar akun kerja yang tertaut ke akun utama.
- `/promo` — (Owner) Membuka menu konfigurasi syarat kata kunci LPM dan link postingan Story.
