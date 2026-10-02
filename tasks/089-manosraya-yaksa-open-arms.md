# Task 089: Fitur Yaksa Open Arms (Manosraya)

**Tujuan**: Membuat fitur baru mirip `menfess` untuk mengirim aspirasi, kritik, atau saran anonim ke channel khusus (Yaksa Open Arms) yang ditujukan ke Dhruva (sistem/pengelola).

**Detail Pengerjaan**:
1. Mengakses `manos_ch_id` dari `.env` dan menyimpannya di konfigurasi `bot/settings.py` sebagai `MANOS_CH_ID`.
2. Menambahkan tabel database baru `manosraya_history` di `bot/database.py` dengan skema `id`, `sender_id`, `message_text`, `created_at` dan *method* penyisipan `add_manosraya` untuk merekam *history* pengiriman.
3. Membuat *handler* Telegram baru `/manosraya` di `bot/handlers/manosraya.py`. Alurnya dibuat *direct prompt* tanpa menu interaktif, sehingga *user* langsung diminta untuk menulis pesannya dan menekan tombol konfirmasi.
4. Memastikan format anonim terjaga ketika di-*forward* ke channel `MANOS_CH_ID` sesuai instruksi, namun `sender_id` tetap terekam di database `manosraya_history` untuk keperluan pelacakan owner. 
5. Tidak ada operasi penambahan/pengurangan poin Agra dalam fitur ini.
6. Mendaftarkan *router* `manosraya.cmd_manosraya_router` di fungsi `register_all` dalam `bot/handlers/register.py`.

**Dokumentasi yang Diperbarui**:
- Memperbarui `docs/commands.md` dengan info penambahan command `/manosraya`.
- Memperbarui `docs/database.md` dengan info struktur tabel baru `manosraya_history`.
