# Implementasi Fitur Menfess

## Tujuan
Menambahkan fitur pengiriman pesan rahasia (menfess) antar pengguna bot. Setiap pengiriman dikenakan tarif 1 Agra, dan pengirim dapat menyertakan bonus Agra (gift) kepada penerima. Pesan dikirimkan ke channel khusus serta melalui private chat ke penerima.

## Perubahan Kode
1. **Database (`bot/database.py`)**
   - Menambahkan tabel `menfess_history` ke dalam `SCHEMA`.
   - Menambahkan metode `add_menfess`, `get_menfess_inbox`, `get_menfess_sent`, dan `get_menfess_by_id`.
2. **Handler Menfess (`bot/handlers/menfess.py`)**
   - Dibuat file baru untuk meng-handle fitur `/menfess`.
   - Menggunakan `ConversationHandler` untuk state flow (Kirim, Target, Pesan, Konfirmasi, Nominal Gift).
   - Mengambil `MENFESS_CH_ID` dari variabel environment (default di `.env`).
   - Menyertakan tautan pos channel (`@DhruvaFess`) untuk pesan yang berhasil dikirim.
   - History menfess ditampilkan tanpa pesan utuhnya (hanya ID dan info singkat). Pesan bisa dibaca secara utuh dengan perintah `/menfess_read <id>`.
3. **Pendaftaran Command (`bot/handlers/register.py`)**
   - Menambahkan pendaftaran untuk `cmd_menfess_router` dan `cmd_menfess_read` ke dalam `register_all`.
4. **Dokumentasi**
   - Memperbarui `docs/commands.md` dan `docs/database.md`.
