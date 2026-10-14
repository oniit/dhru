# Task: Preserve Core Profile Fields on Role Change

## Latar Belakang
User menyadari bahwa jika ada perpindahan *role* (seperti `student` mendaftar menjadi `charyarthi` atau mendaftar `maba`), bot seringkali menghapus beberapa field (misal: `muse`, `birth_date`) yang sudah diisi karena field tersebut secara teknis tidak tercantum sebagai field wajib untuk role transisi/baru tersebut. Hal ini memaksa pengguna untuk menginput ulang "Nama, TTL, dan Muse" setelah kembali ke *role* asalnya atau saat registrasi lanjutan. 
Selain itu, perintah `/maba` dan registrasi *Charyarthi* masih di-*hardcode* untuk menanyakan *Nama Lengkap* (menimpa yang lama) bahkan jika *full_name* sudah terisi di database.

## Pekerjaan yang Dilakukan
- Memodifikasi fungsi `_revalidate_filtered_choice_fields` di `bot/handlers/commands.py`. Sesuai dengan instruksi terbaru, fungsi ini secara eksplisit **tidak akan menghapus** data fundamental profil pengguna berikut meskipun *role* berubah: `birth_date`, `muse`, `join_reason` (alasan maba), dan `charyarthi_reason` (alasan staf).
- **Penyesuaian (Feedback User):** Kolom `major` (Jurusan), `student_id` (NIM), dan `club_enrolled` (UKM) **sengaja dibiarkan terhapus** saat pengguna keluar dari role *Student*. Hal ini disengaja agar di masa depan, jika pengguna kembali menjadi mahasiswa dengan *generasi yang berbeda* (NIM baru), mereka diwajibkan untuk menginput ulang NIM mereka untuk menjaga akurasi data antar generasi.
- Menambahkan field baru `charyarthi_reason` ke dalam sistem profil (`config/profile_fields.yaml`). Field ini menyimpan alasan pengguna mendaftar menjadi staf, dan ditampilkan ke admin penyeleksi pada saat konfirmasi pengajuan Charyarthi.
- Memodifikasi alur registrasi MABA (`maba:start` callback) untuk memeriksa apakah `full_name` sudah ada. Jika ada, lewati pertanyaan "Nama Lengkap" dan langsung menuju pengisian alasan.
- Memodifikasi alur registrasi Charyarthi (`charyarthi:start` callback) untuk memeriksa `full_name`. Jika sudah ada, lewati pertanyaan nama, lanjut untuk menanyakan alasan (`charyarthi_reason`), lalu tampilkan *keyboard* pemilihan Divisi.

## Teknis
- Dalam `commands.py` pada loop `_revalidate_filtered_choice_fields`, menambahkan kondisi: `if f.key in ("birth_date", "muse", "join_reason", "charyarthi_reason"): continue`.
- Dalam `commands.py`, jika `prof.get("full_name")` tersedia, *onboarding_step* pendaftaran langsung diloncati ke tahap `CHARYARTHI_REASON` atau `MABA_REASON` untuk mempercepat *flow*.
- Mengupdate pembuatan pesan `msg_admin` saat user klik Submit Charyarthi agar mencantumkan alasan mendaftar yang baru.

### Fitur Role Purva & Manajemen SKS Lintas Generasi
- Mendaftarkan konstanta `ROLE_PURVA = "purva"` secara resmi di `database.py` dan `common.py` (dengan nama label Purvashishya).
- **Sifat Profil:** Role ini berperilaku mirip dengan `public` (yaitu field spesifik seperti NIM, UKM, dan Jurusan akan dikosongkan/terhapus otomatis).
- **Perhitungan SKS (*Banking System*):** Ketika user menjadi Purva (alumni), total SKS yang pernah dikumpulkan otomatis tetap tersimpan aman di profil sebagai *accumulated_sks* (saldo SKS statis) meskipun field penyumbang SKS-nya terhapus.
- **Re-enrollment Skenario:** Jika mereka kelak mendaftar lagi menjadi mahasiswa dengan NIM generasi berjalan yang baru, SKS baru akan ditambahkan (di-*sum*) ke `accumulated_sks` lama tersebut secara otomatis menjadi `total_sks`.
