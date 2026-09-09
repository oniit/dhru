# Task 072: Maba Code Notification to Backup Channel & Userbot Auto-Update

## Tujuan
1. Mengirimkan notifikasi ke `BACKUP_CH_ID` ketika ada kode akses dengan target role `maba` yang digunakan. Format pesan mirip dengan notifikasi ke owner, tetapi tanpa field ID dan Role.
2. Membaca pesan notifikasi ini melalui `checker.py` (Userbot) lalu mengedit daftar post kode manual yang ada di `BACKUP_CH_ID` untuk menambahkan label `(telah diklaim)` di sebelah kode yang berhasil diklaim.

## Apa yang Dikerjakan
- Mengedit `bot/handlers/messages.py` untuk mengimpor `BACKUP_CH_ID` dari `bot.settings`.
- Menggunakan `update.effective_user` untuk mengekstrak informasi yang dibutuhkan (nama, username) sebelum pengecekan ke `OWNER_ID`.
- Menambahkan kondisi jika `target_role` adalah "maba" dan `BACKUP_CH_ID` tersedia (tidak kosong), bot akan mengirimkan pesan berisi informasi penggunaan kode akses.
- Menambahkan *event listener* `on_message` pada `checker.py` dengan *filter* `BACKUP_CH_ID` yang memantau adanya kata "Kode Akses Digunakan".
- Userbot akan mengekstrak kode yang diklaim, lalu mencari riwayat pesan di channel tersebut (post manual admin) dan melakukan `edit_text` untuk menambahkan teks `(telah diklaim)` menggunakan Regex.

## Alasan Teknis
Sesuai permintaan user, fitur ini membuat admin tidak perlu lagi me-refresh atau mengupdate status ketersediaan kode secara manual. Userbot yang memiliki akses admin ke channel secara mandiri mendeteksi notifikasi dari bot utama lalu secara otomatis memperbarui status kode pada postingan manual daftar kodenya.
