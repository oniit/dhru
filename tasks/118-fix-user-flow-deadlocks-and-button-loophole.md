# Task 118: Fix User Flow Deadlocks, Button Loopholes & Race Conditions

## Latar Belakang
Audit mendalam terhadap pengalaman pengguna (*User Experience / User Journey*) menemukan beberapa potensi celah logika (*logical flaws*), urutan alur yang berisiko (*race conditions*), serta tombol yang berpotensi terkunci (*deadlock*):
1. **Deadlock Divisi Tanpa Soal**: Jika sebuah divisi tidak memiliki soal tes esai tertulis (`total_q == 0`), tombol terkunci pada `⏳ Belum Lengkap (0/0)` dengan callback `not_ready`, sehingga pelamar tidak pernah bisa melanjutkan pendaftaran.
2. **Celah Bypass via Menu Pratinjau**: Pada menu *Pratinjau*, tombol `🚀 Lanjut ke Berkas & Submit` selalu muncul meskipun jawaban belum lengkap, memungkinkan pelamar melewati tahapan tes.
3. **Ketiadaan Validasi Server-Side saat Final Submit**: Handler `charyarthi:submit` hanya mengecek validasi promosi (`promo_count < 1`), namun tidak memverifikasi kelengkapan jawaban tes divisi pelamar.
4. **Keputusan Ganda Admin (Race Condition)**: Menekan tombol "Terima" atau "Tolak" berulang kali atau oleh dua admin berbeda dapat memproses ulang penerimaan atau secara tidak sengaja me-rollback staf yang sudah diterima ke publik.
5. **Ketiadaan Perintah Batal Global (`/cancel` / `/batal`)**: Pengguna yang berada dalam *state* input teks tidak memiliki perintah pembatalan standar jika ingin keluar dari alur pengisian.
6. **Tombol Loading Spinner Abadi**: Jika ada *callback data* yang tidak cocok dengan percabangan handler, `query.answer()` tidak terpanggil, menyebabkan tombol Telegram menampilkan animasi putaran (*loading spinner*) terus-menerus.

---

## Perubahan & Implementasi Teknis

### 1. Perbaikan Alur Kuis Divisi (`bot/handlers/common.py` & `commands.py`)
- Pada `render_charyarthi_quiz_view`:
  - Jika `total_q == 0`, tampilkan informasi ramah: *"Divisi ini tidak memerlukan tes studi kasus tertulis khusus. Anda dapat langsung melanjutkan ke pengisian berkas dan submit pendaftaran."*
  - Tombol langsung membuka `🚀 Lanjut ke Berkas & Submit`.
- Pada `charyarthi:preview`:
  - Mengevaluasi `answered_count` terhadap `total_q`. Tombol submit hanya aktif jika seluruh soal telah terisi. Jika belum lengkap, tombol berubah menjadi `⏳ Belum Lengkap` (`charyarthi:not_ready`).

### 2. Validasi Server-Side pada Final Submit (`bot/handlers/commands.py`)
- Pada `charyarthi:submit`:
  - Mengambil daftar soal divisi `target_division_1` dan mencocokkan dengan `charyarthi_answers`.
  - Jika masih ada soal yang kosong, submit ditolak dengan alert: *"Soal tes divisi Anda belum lengkap (X/Y terisi). Harap selesaikan tes sebelum submit!"*.

### 3. Proteksi Keputusan Admin Ganda (`bot/handlers/commands.py`)
- Pada callback `charyarthi:acc` dan `charyarthi:rej`:
  - Mengecek apakah status pelamar sudah `ACCEPTED` atau `REJECTED`, atau role bukan lagi `ROLE_CHARYARTHI`.
  - Jika sudah diputuskan, bot memunculkan alert *"⚠️ Lamaran ini sudah pernah diputuskan sebelumnya"*, menghentikan pemrosesan ganda, dan menghapus *inline keyboard*.
- Mengupdate pengujian otomatis `tests/test_charyarthi.py` untuk memvalidasi proteksi keputusan ganda ini.

### 4. Perintah Pembatalan Global (`/cancel` & `/batal`)
- Menambahkan fungsi `cmd_cancel` di `bot/handlers/commands.py`:
  - Menghapus `onboarding_step` pengguna di database (`None`).
  - Membersihkan *temporary data* pada `context.user_data`.
  - Mengirim pesan konfirmasi pembatalan.
- Mendaftarkan handler `CommandHandler(["cancel", "batal"], commands.cmd_cancel)` pada `bot/handlers/register.py`.

### 5. Fallback Anti Loading Spinner
- Menambahkan blok fallback `try: await q.answer() except Exception: pass` pada akhir `on_callback` di `commands.py` dan `cb_kontrak` di `kontrak.py`.
- Memastikan setiap interaksi tombol selalu mendapatkan *acknowledgment* instan dari bot.
