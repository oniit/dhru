# Task 084: Add Menfess Character Limit

## Deskripsi
Menambahkan limitasi panjang karakter pada fitur menfess untuk mencegah error Telegram API ketika pesan melebihi 4096 karakter. Jika user mengirim lebih dari 4000 karakter, bot akan memberikan peringatan dan meminta penulisan ulang.

## Perubahan Kode
- **`bot/handlers/menfess.py`**:
  - Menambahkan pengecekan `len(text) > 4000` di fungsi `message_handler`.
  - Mengembalikan state `MESSAGE` dengan warning jika melebihi batas.
