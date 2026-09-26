# Task 083: Fix Kick Command Bug (Tidak Terbaca/Gagal Eksekusi)

## Deskripsi
Pengguna melaporkan bahwa command `/kick` terkadang "tidak terbaca" atau tidak memberikan respons (silent failure). Bug ini disebabkan oleh dua hal:
1. `update.message.text` bernilai `None` saat user membalas pesan menggunakan file media (seperti foto/video) dengan menyertakan *caption* `/kick`. Metode `.strip()` menyebabkan program crash (AttributeError) secara diam-diam.
2. Pengecekan otorisasi `pos == "d_sekre"` gagal bekerja sebagaimana mestinya ketika atribut `position_detail` milik user berbentuk `list` (karena user memegang jabatan rangkap), sehingga user *sekre* yang legal terblokir dengan pesan "Anda tidak memiliki izin".

## Perubahan Kode
- **`bot/handlers/commands.py`**:
  - Mengubah cara membaca pesan di `cmd_kick` dari `update.message.text.strip()` menjadi `(update.message.text or update.message.caption or "").strip()` agar dapat menangani pesan berupa media ber-caption.
  - Memperbarui mekanisme pemeriksaan `d_sekre` menggunakan operator `in` jika tipe datanya berupa `list`, sehingga meskipun user mempunyai banyak jabatan, aksesnya tetap diizinkan.
  - Menambahkan dukungan multi-target (beberapa username/ID yang dipisahkan spasi) pada command `/kick` sekaligus membuat laporan rekapitulasinya.
