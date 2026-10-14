# Task 108: Fix NameError 'presence_allowed_class_ids' in cmd_help and Improve Broadcast Queue Resilience

## Ringkasan Masalah
Pada runtime bot Telegram (`main.py`), terjadi error fatal ketika pengguna memanggil perintah `/help`:
```
ERROR __main__ Exception saat memproses update: name 'presence_allowed_class_ids' is not defined
Traceback (most recent call last):
  ...
  File "bot/handlers/commands.py", line 548, in cmd_help
    await update.message.reply_text(help_for_role(role, profile))
  File "bot/handlers/commands.py", line 441, in help_for_role
    allowed_classes = presence_allowed_class_ids(role, prof)
NameError: name 'presence_allowed_class_ids' is not defined
```

Selain itu, pada log scheduler `process_broadcast_queue`, antrean pengiriman broadcast mencatat `400 Bad Request` dari Telegram API secara berulang tanpa informasi logging yang memadai untuk proses diagnostik serta ketiadaan fallback teks biasa apabila HTML parsing gagal.

## Analisis Masalah
1. **NameError `presence_allowed_class_ids`**:
   - Di `bot/handlers/commands.py` pada fungsi `help_for_role`, fungsi `presence_allowed_class_ids(role, prof)` dipanggil untuk memfilter tampilan menu presensi sesuai hak akses pengguna.
   - Namun, `presence_allowed_class_ids` yang didefinisikan di `bot/handlers/common.py` belum diimpor ke dalam `bot/handlers/commands.py`.
   - Di samping itu, logger di `bot/handlers/commands.py` belum didefinisikan secara global (`log` dan `logger`), yang berisiko memicu `NameError` pada `cmd_export_photos` ketika error terjadi.
2. **Broadcast Queue Resilience**:
   - Di `bot/jobs.py` pada `process_broadcast_queue`, pengiriman pesan broadcast yang mengalami `BadRequest` akibat error parsing format HTML langsung di-swallow dan di-drop tanpa retry teks biasa dan tanpa logging detail ID penerima serta deskripsi errornya.

## Solusi & Perubahan Teknis
1. **Import `presence_allowed_class_ids`**:
   - Menambahkan import `presence_allowed_class_ids` dari `bot.handlers.common` ke dalam `bot/handlers/commands.py`.
   - Menginisialisasi `log = logging.getLogger(__name__)` dan `logger = log` di level modul `bot/handlers/commands.py`.
2. **Error Handling & Fallback di `process_broadcast_queue`**:
   - Di `bot/jobs.py`, menambahkan penanganan `BadRequest`. Jika pesan ditolak Telegram karena kesalahan entitas HTML (`can't parse entities`), sistem secara otomatis melakukan fallback pengiriman pesan sebagai plain text tanpa `parse_mode="HTML"`.
   - Menambahkan logging warning terperinci saat pengiriman broadcast gagal ke user tertentu.
3. **Pengujian (Regression Test)**:
   - Menambahkan fungsi tes `test_cmd_help_all_roles` di `tests/test_deep_qa.py` yang memvalidasi `help_for_role` dan handler `cmd_help` pada seluruh role (Student, Admin, Owner, Internal, BEM, Maba, Charyarthi, Purva, Public).
   - Seluruh pengujian pytest berhasil lolos 100%.
