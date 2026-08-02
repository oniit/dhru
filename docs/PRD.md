# Product Requirements Document (PRD)

## Ringkasan Eksekutif
Bot Manajemen Akademik Telegram dirancang untuk menjadi asisten utama bagi mahasiswa, dosen, dan staf di sebuah lingkungan kampus/fakultas. Bot ini mengautomasi proses administrasi seperti pendaftaran profil, absensi (presensi) perkuliahan, manajemen tugas, serta sistem poin (Agra) untuk gamifikasi dan _reward_.

## Tujuan
1. **Automasi Administrasi**: Mengurangi beban kerja staf untuk pendataan mahasiswa dan absensi.
2. **Keterlibatan (_Engagement_)**: Mendorong keaktifan mahasiswa melalui sistem poin (Agra) yang dapat dipertukarkan dengan keuntungan akademik/sosial.
3. **Manajemen Tugas Sentralisasi**: Memudahkan dosen/asisten memberikan dan memeriksa tugas langsung dari dalam Telegram.

## Fitur Utama

### 1. Onboarding & Manajemen Profil (`/start`, `/lengkapi`)
- Bot mendukung alur registrasi yang dinamis berdasarkan peran (Role) yang diberikan.
- **NIM Generator**: Men- _generate_ NIM (`student_id`) secara otomatis berdasarkan kode Fakultas, Jurusan, Kode Angkatan (`GENERATION_CODE`), dan urutan mendaftar.
- **Persetujuan Profil**: Perubahan data kritis diajukan dalam _queue_ untuk disetujui oleh HR/SDM (`d_umum_sdm`).

### 2. Presensi Perkuliahan (`/presensi`)
- Dosen atau staf (dengan izin terkait) dapat "membuka" presensi.
- Mahasiswa mencatatkan presensi. Sistem melacak status (Hadir, Izin, Terlambat, Alfa).
- Pengguna yang presensi mendapatkan poin **Agra**.

### 3. Manajemen Tugas (`/tugas`)
- Pengajar (Dosen, Guru Besar, Coach) dapat mengunggah tugas dengan batas waktu (_deadline_).
- Mahasiswa mengunggah jawaban (teks atau berkas) melalui _bot_.
- Pengajar me- _review_ (Terima/Tolak). Menerima tugas memberikan poin Agra kepada mahasiswa.

### 4. Poin Agra
- Sistem mata uang/poin virtual yang didapatkan dari keaktifan: Presensi (Hadir/Izin), Melengkapi profil, Mengumpulkan Tugas.
- Transaksi dilacak via `audit_logs` dan `agra_history`.

## Peran (Roles) & Akses
1. **Owner / Founder**: Akses penuh ke sistem, termasuk menu reset massal dan persetujuan.
2. **Admin (Sekretaris)**: Akses super untuk moderasi dan manajemen data umum.
3. **Staff (Internal)**: Staf kampus (Dekan, Dosen, Guru Besar, Coach, dan staf umum) yang memiliki hak mengelola tugas, absen, dan rekapitulasi.
4. **Student (Mahasiswa)**: Pengguna reguler yang mengikuti kelas, presensi, dan tugas. Memiliki NIM, data jurusan, dan KRS/SKS.
5. **BEM**: Pada dasarnya adalah Mahasiswa (memiliki NIM, SKS, dll), namun memiliki hak istimewa (fitur staf) tambahan, seperti kemampuan melakukan siaran pesan (Broadcast) dan fitur organisasi lainnya.
6. **Public**: Tamu yang tidak terafiliasi dengan fakultas.
