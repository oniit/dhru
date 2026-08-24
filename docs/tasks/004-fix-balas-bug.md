# Task 004: Fix #balas Silent Crash

## Latar Belakang
Pengguna melaporkan bahwa fitur balas pesan menggunakan `#balas` dari grup Petinggi gagal terkirim tanpa pesan *error* apapun ("gada respon"). Saat pesan dibalas dengan format yang benar sekalipun, pesan bot sama sekali tidak muncul. 

## Analisis Masalah
Melalui proses *debugging* dengan bantuan *interceptor*, ditemukan bahwa pesan dari Petinggi memang berhasil diterima bot, namun gagal dieksekusi di fungsi utama (`messages.on_group_message`).

Penyebab utamanya adalah **Handler Conflict** (konflik filter penanganan pesan) akibat penambahan fitur "Promo" sebelumnya:
- Fungsi pengaturan promo (`promo_text_handler`) didaftarkan ke `group=2` (lapis yang sama dengan `#balas`).
- Filter yang digunakan untuk `promo_text_handler` adalah `filters.TEXT & ~filters.COMMAND`, yang secara keliru **menangkap semua pesan teks dari semua grup** (bukan hanya *Private Message*).
- Karena didaftarkan sebelum `#balas`, `promo_text_handler` akan mencegat pesan teks apapun (termasuk `#balas`), lalu keluar secara diam-diam (`return None`) jika kriteria promo admin tidak aktif. Hal ini menghentikan pesan untuk diteruskan ke handler selanjutnya, sehingga `#balas` sama sekali tidak pernah dipanggil.

Selain itu, ditambahkan juga izin (*authorization*) pada `on_group_message` agar `#balas` bisa tetap bekerja di dalam *Discussion Group* yang terhubung ke Channel Petinggi.

## Solusi yang Diimplementasikan
1. **Memperbaiki Filter Promo**: Mengubah *filter* `promo_text_handler` di `bot/handlers/promo.py` dengan menambahkan `filters.ChatType.PRIVATE`. Dengan begitu, fitur *setup* promo admin tidak lagi membajak pesan teks dari dalam Grup/Channel.
2. **Memperbaiki Otorisasi `#balas`**: Mengubah fungsi `on_group_message` di `messages.py` untuk mengizinkan instruksi `#balas` dijalankan di luar ID Grup utama asalkan pengguna tersebut memiliki status Admin (bisa membalas di grup diskusi manapun).
3. **Penyempurnaan Pesan Error**: Menambahkan respons error spesifik (misal: "Anda harus me-reply pesan dari bot") jika format penggunaan `#balas` tidak memenuhi syarat.

## Status
Fitur `#balas` sudah kembali beroperasi normal tanpa intervensi.
