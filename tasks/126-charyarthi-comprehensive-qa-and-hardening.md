# Task 126: Chāryārthī Registration Flow Comprehensive QA & Hardening

## 1. Overview & Context
Melakukan proses Quality Assurance (QA) mendalam dan holistik terhadap seluruh arsitektur dan siklus hidup pendaftaran calon staf (**Chāryārthī**) serta instrumen pendukungnya:
- Jalur pendaftaran pelamar (alur nama, alasan, pemilihan & penguncian divisi, tes soal esai, pratinjau jawaban per nomor maupun ringkasan, promosi LPM/Story, dan pengiriman formulir).
- Penyaluran data lamaran ke channel pendaftar (`PENDAFTAR_CH_ID`) dan channel tim SDM (`SDM_CH_ID`).
- Panel wewenang dan pengelolaan soal tes calon staf (`/soal`, `/setsoal`, `/tambah_soal`, `/hapus_soal`, `/reset_soal`).
- Keputusan kelulusan (`/acc_charyarthi`, `/reject_charyarthi`, inline callback `charyarthi:acc`, `charyarthi:rej`).

Semua pengujian mematuhi aturan QA workspace (bebas pesan ke pengguna produksi nyata, menggunakan mock update dan database dev Turso remote).

---

## 2. Issues Discovered During Deep QA & Resolutions

### A. State Persistence / Menjebak Admin pada `INPUT_SOAL_ADD`
- **Temuan**: Saat admin mengklik tombol `➕ Tambah 1 Soal` di menu `/soal`, `onboarding_step` admin disetel ke `INPUT_SOAL_ADD:{div_id}`. Namun jika admin menekan tombol navigasi lain seperti `❌ Batal`, `🔙 Pilih Divisi Lain`, `🗑️ Hapus Soal`, atau `❌ Tutup Menu`, status `onboarding_step` tidak dibersihkan. Akibatnya, pesan teks biasa apa pun yang dikirim admin di private chat berikutnya secara keliru tersimpan sebagai soal tes divisi tersebut.
- **Solusi**: Menambahkan pembersihan otomatis `onboarding_step` pada callback `soal:` untuk semua sub-aksi selain `adm_add`.

### B. Tag HTML Mentah pada Placeholder Pratinjau Soal Belum Terisi
- **Temuan**: Pada `charyarthi:preview`, pertanyaan yang belum diisi mengambil nilai default `"<i>(Belum diisi)</i>"`. Teks ini kemudian dilewatkan ke `html.escape(ans)`, mengubahnya menjadi `"&lt;i&gt;(Belum diisi)&lt;/i&gt;"`. Di layar Telegram pengguna, teks tersebut tampil sebagai kode tag mentah dan bukan cetak miring.
- **Solusi**: Memperbaiki logika `charyarthi:preview` agar hanya melakukan `html.escape` jika jawaban benar-benar diisi; untuk yang belum diisi langsung menggunakan format `<i>(Belum diisi)</i>` yang valid.

### C. Proteksi Panjang Karakter Telegram (Batas 4096) pada Threaded Reason Reply
- **Temuan**: Pada penerusan kartu pendaftar ke `PENDAFTAR_CH_ID`, jika alasan pendaftar panjang (> 600 karakter), bot mengirim balasan berantai (*threaded reply*). Teks alasan diekstrak dengan `raw_reason[:3800]`. Jika teks mengandung banyak karakter HTML yang memuai saat di-*escape* (seperti `&`, `<`, `>`) atau digabung dengan header dan blok kutipan, panjang teks dapat melampaui 4.096 karakter dan menyebabkan error `BadRequest: Message is too long`.
- **Solusi**: Membatasi panjang teks yang telah di-*escape* secara ketat ke $\le 3.200$ karakter dengan penanda potong yang elegan, memastikan seluruh muatan pesan berantai selalu berada di bawah 3.500 karakter.

### D. Notifikasi SDM untuk Divisi Tanpa Tes Esai Tertulis (0 Soal)
- **Temuan**: Jika seorang pelamar mendaftar untuk divisi yang belum memiliki soal tes esai tertulis (atau memang tidak memerlukan tes esai, misal Biro Sarpras atau Eksternal), blok pengiriman ke `SDM_CH_ID` sebelumnya diabaikan (`if questions:` bernilai False), sehingga tim SDM tidak menerima rekapitulasi data pendaftar tersebut.
- **Solusi**: Menambahkan kartu notifikasi khusus ke `SDM_CH_ID` ketika pelamar mendaftar ke divisi dengan 0 soal tes esai, mengabarkan bahwa berkas telah disubmit dan divisi tersebut tidak memerlukan tes studi kasus tertulis tambahan.

### E. Pencegahan Overflow Karakter pada Menu Overview Soal Admin
- **Temuan**: Fungsi `_render_admin_division_soal` menampilkan daftar seluruh pertanyaan dalam satu pesan. Jika satu divisi memiliki 15–25 pertanyaan panjang, total karakter pesan menu admin dapat melampaui batas 4.096 karakter dan menggagalkan `edit_message_text`.
- **Solusi**: Membatasi pratinjau teks tiap soal hingga 140 karakter pada tampilan ringkasan admin dan membatasi total string maksimal 3.400 karakter dengan indikator `... dan N soal lainnya`.

### F. Validasi Input Kosong pada Onboarding Chāryārthī
- **Temuan**: Pengguna yang mengirimkan spasi kosong atau pesan tanpa teks saat berada di step `CHARYARTHI_NAME`, `CHARYARTHI_REASON`, atau `CHARYARTHI_ANS:` sebelumnya diterima begitu saja dengan nilai string kosong.
- **Solusi**: Menambahkan validasi `if not text` di `bot/handlers/messages.py` yang meminta pengguna mengisi teks nyata sebelum melanjutkan.

### G. Pembersihan Status `REJECTED` Saat Memulai Pendaftaran Baru
- **Temuan**: Pengguna yang sebelumnya pernah ditolak (memiliki status profil `"REJECTED"`) dan ingin mendaftar kembali saat OPREC masih dibuka masih menyimpan flag `"REJECTED"` di profil draft-nya.
- **Solusi**: Mengosongkan `application_status` menjadi `None` saat pengguna memulai ulang alur pendaftaran via `charyarthi:start` atau `/charyarthi`.

### H. Penambahan Perintah `/charyarthi`
- **Fitur**: Menambahkan perintah `/charyarthi` untuk memberikan kemudahan bagi pengguna publik yang ingin langsung memulai pendaftaran via perintah teks, setara dengan perintah `/maba`.

---

## 3. Verifikasi & Pengujian
Seluruh perbaikan diuji secara otomatis dalam file tes `tests/test_charyarthi.py` (10 test cases, mencakup kasus batas panjang teks, siklus database, toggle dinamis, dan QA komprehensif).
