# Task 109: Transparansi ID Divisi Chāryārthī & Akses Pengelolaan Soal untuk Staf Internal

## Ringkasan Masalah
1. **Staf Tidak Bisa Menambah Soal Divisi**:
   - Fungsi otorisasi `_can_manage_soal` sebelumnya membatasi akses hanya kepada `ROLE_OWNER`, `ROLE_ADMIN`, pemegang jabatan `d_hrd`, atau pesan di grup `SDM_GID`/`PETINGGI_GID`.
   - Akibatnya, anggota staf ber-role `internal` (misal koordinator editor, dosen, sarpras, eksternal) yang berinteraksi di Private Chat (DM) dengan bot ditolak dengan pesan: `⛔ Perintah ini hanya dapat diakses oleh Tim SDM dan Petinggi.`
2. **Ketiadaan Informasi Variabel ID Divisi**:
   - Menu utama `/soal` hanya menampilkan tombol label divisi (seperti "Editorial & Konten", "Pengembangan SDM"), namun tidak mencantumkan teks ID variabel yang valid.
   - Staf bingung harus menggunakan identifier apa saat memanggil perintah teks seperti `/tambah_soal <divisi> <teks>` atau `/setsoal <divisi>`.

## Solusi & Perubahan Teknis
1. **Perluasan Akses Otorisasi Staf (`_can_manage_soal` & `on_callback`)**:
   - Menambahkan `u_row["role"] in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL)` pada pemeriksaan otorisasi di `bot/handlers/commands.py`.
   - Seluruh anggota staf internal kini diizinkan mengelola pertanyaan tes divisi baik melalui Private Chat (DM) maupun grup.
2. **Transparansi Variabel ID Divisi**:
   - Di menu utama `/soal`, kini ditampilkan daftar lengkap nama divisi beserta ID variabelnya (`editor`, `hrd`, `eksternal`, `sarpras`, `dosen`, `coach`, `lain`).
   - Di tampilan detail divisi (`_render_admin_division_soal`), dicantumkan baris `🔑 ID Variabel: <code><id></code>`.
   - Pada pesan bantuan dan pesan error `cmd_soal`, `cmd_setsoal`, `cmd_tambah_soal`, `cmd_hapus_soal`, dan `cmd_reset_soal`, ditambahkan ringkasan ID divisi yang valid jika argumen tidak cocok.
   - Pada prompt inline `[ ➕ Tambah 1 Soal ]`, ditambahkan petunjuk format perintah cepat `/tambah_soal <id> <pertanyaan>` jika tombol diklik di dalam grup.
3. **Dokumentasi**:
   - Memperbarui `docs/commands.md` agar mencantumkan bahwa perintah `/soal`, `/setsoal`, `/tambah_soal`, `/hapus_soal`, dan `/reset_soal` dapat diakses oleh Staf Internal beserta daftar ID divisinya.
