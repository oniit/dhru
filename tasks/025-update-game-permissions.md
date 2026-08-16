# Update Game Permissions

## Apa yang Dikerjakan
Mengubah izin akses untuk command game (`/bermain` dan `/berhenti`) agar lebih fleksibel dan interaktif untuk semua anggota grup. 

## Mengapa Dikerjakan
Atas permintaan pengguna (user), command `/bermain` harus bisa digunakan oleh siapa saja di dalam grup, bukan hanya admin. Selain itu, command `/berhenti` harus dapat diakses oleh pemulai game (user yang menjalankan `/bermain`), bukan hanya admin. Hal ini untuk memudahkan anggota grup dalam bermain tanpa selalu bergantung pada admin grup.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Game State Modifikasi (`bot/games/kata_rahasia.py`)**:
   - Pada fungsi `mulai_kata_rahasia`, state awal (`initial_state`) yang disimpan ke database sesi game (tabel `game_sessions`) sekarang menyimpan key baru: `"started_by": update.effective_user.id`. Ini bertujuan untuk merekam siapa user yang memulai game tersebut.
2. **Permission Check Update (`bot/handlers/games.py`)**:
   - Pada fungsi `cmd_bermain`, pengecekan `_is_admin` dihapus sehingga semua user di grup dapat memanggil command `/bermain`.
   - Pada fungsi `cmd_berhenti`, pengecekan `_is_admin` dipindah ke bawah setelah bot mengambil data `session` dari database. Bot kemudian mengecek `state_json` untuk membaca `started_by`. Izin diberikan jika user adalah admin (`_is_admin`) ATAU user adalah pemulai game (`is_starter`).
