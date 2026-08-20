# 033 Kontrak Owner Notification

## Deskripsi
Menambahkan fitur notifikasi otomatis ke `OWNER_ID` setiap kali ada staf yang baru mengisi atau memperbarui (renew) kontrak kerjanya.

## Alasan
Owner (founder) perlu mengetahui secara real-time kapan seorang staf menyetujui dan mengisi kontrak, tanpa harus selalu mengecek melalui perintah admin `/kontrak all`.

## Implementasi Teknis
- Memodifikasi fungsi `_generate_and_send_kontrak` di dalam `bot/handlers/kontrak.py`.
- Setelah bot berhasil mengirimkan gambar kontrak beserta detailnya ke staf (atau menyimpannya di database), bot akan melakukan pengecekan `is_admin_check`. Jika bukan admin yang mengecek, maka itu adalah proses generate sungguhan oleh staf.
- Bot akan mengambil nilai `OWNER_ID` dari environment/setting.
- Bot akan mengirimkan gambar kontrak yang baru di-generate (`BytesIO(png_bytes)`) beserta *caption* berisi detail nama, username, dan masa berlaku kontrak secara langsung ke Private Chat Owner.
