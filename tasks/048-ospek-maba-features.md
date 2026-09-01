# Tugas Maba dan Presensi Harian Ospek

## Deskripsi
Fitur tambahan khusus kegiatan Ospek Mahasiswa Baru (Maba) yang di-request oleh user. Mencakup fungsionalitas penugasan dengan reward spesifik, dan presensi otomatis per kelompok.

## Poin Perubahan

1. **Jabatan Baru & Kelas Baru**
   - Menambahkan `p_panitia_ospek` di `position_details` (setara dosen dalam manajemen tugas).
   - Menambahkan `ospek_maba` di pilihan `classes` (digunakan sebagai penugasan khusus).

2. **Reward Tugas Maba**
   - Memodifikasi `AGRA_REWARD_TUGAS_MABA = 15` di `settings.py` dan `rewards.yaml`.
   - Update `bot/handlers/tugas.py` agar mengalokasikan reward 15 (bukan 35) apabila kelas dari tugas tersebut adalah `ospek_maba`.

3. **Presensi Harian Maba (Ospek Mode)**
   - **Database**: Menambahkan kolom `extra_data` bertipe TEXT di tabel `attendance_sessions` menggunakan skema migrasi `ALTER TABLE` pada saat inisialisasi agar menyimpan info pesan kelompok. 
   - Ditambahkan fungsi helper `set_attendance_extra_data` di `database.py`.
   - **Command Mode**: Pembuatan `cmd_ospek_mode` (on/off) untuk mentrigger / mendisable _job schedule_ otomatis. Command ini di-_register_ pada `register.py`.
   - **Job Scheduler**: 
     - Menambahkan fungsi `daily_maba_attendance_open` yang tereksekusi pada 15:00.
     - Fungsi ini membuat 1 sesi utama, lalu mengirim broadcast paralel ke seluruh ID grup kelompok (`MABA_GROUP_GIDS`) yang dicatat _message_id_-nya ke dalam _extra_data_ berbentuk JSON.
     - `daily_maba_attendance_close` dijadwalkan pada 22:00.
   - **Handler Callback**: 
     - Modifikasi `cb_attendance_action` dan `_record_hadir` di `bot/handlers/attendance.py` agar mengizinkan Maba mengikuti kelas `maba_auto`.
     - Fungsi baru `refresh_maba_presensi_announcement` dibuat untuk mem-filter tampilan _list_ per kelompok. Pesan Global (semua Maba) diteruskan ke `PRESENCE_CH_ID`, sedangkan pada grup kelompok, pesan akan di-_edit_ hanya untuk menampilkan anggota kelompok masing-masing (berbasis field `maba_group`).
     - Alokasi Agra reward `maba_auto` ditetapkan ke angka 5 Agra.
