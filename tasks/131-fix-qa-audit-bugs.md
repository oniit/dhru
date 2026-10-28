# Task 131: Perbaikan Seluruh Bug Temuan Audit QA & Isolasi Pengujian

## Ringkasan Eksekutif
Berdasarkan laporan audit sistem komprehensif pada [`tasks/130-deep-production-system-qa-audit.md`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tasks/130-deep-production-system-qa-audit.md), seluruh 6 bug dan ketidakkonsistenan yang teridentifikasi telah diperbaiki secara tuntas. Selain itu, masalah kontaminasi state pengujian (`bot.settings.OWNER_ID` global mutation dan *unclosed DB connections*) yang menyebabkan *flaky tests* berhasil ditemukan dan diperbaiki hingga seluruh test suite (58 tes) lulus 100% (58 passed, 0 failed).

---

## Rincian Perbaikan

### 1. BUG-001 [HIGH]: Penanganan Turso `KeyError: 'result'` pada Pelanggaran UNIQUE Constraint
- **File**: [`bot/database.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/database.py)
- **Masalah**: Pada koneksi Turso remote via `libsql_client` HTTP, respons error untuk duplikasi kunci unik tidak membangkitkan `aiosqlite.IntegrityError`, melainkan melempar `KeyError: 'result'` saat mengakses `response["result"]`. Akibatnya, blok penanganan duplikasi di `record_attendance`, `submit_task`, dan `add_linked_account` crash alih-alih melakukan fallback/update.
- **Solusi**:
  - Menambahkan fungsi helper `_is_integrity_error(e: Exception) -> bool` yang memvalidasi baik `aiosqlite.IntegrityError`, `KeyError: 'result'`, maupun string representasi `unique constraint failed` / `constraint failed`.
  - Memperbarui blok `except` pada ketiga fungsi di atas untuk menangkap exception secara aman dan mengecek integritas menggunakan helper sebelum memutuskan re-raise.

### 2. BUG-002 [MEDIUM]: Inkonsistensi String Hasil Game Caksoria
- **File**: [`bot/games/caksoria.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/games/caksoria.py), [`tests/test_caksoria.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_caksoria.py)
- **Masalah**: Fungsi `job_end_caksoria` menggunakan keterangan `f"👺 Salah / kurang dari {delay_min} detik"`, sedangkan fungsi `hasil_caksoria` menggunakan `"👺 Salah / belum waktunya"`.
- **Solusi**:
  - Mengambil parameter `delay_min = state.get("delay_min", "?")` pada `hasil_caksoria` dan menyelaraskan keterangannya menjadi `f"👺 Salah / kurang dari {delay_min} detik"`.
  - Menyelaraskan assertion pada tes unit `test_caksoria.py`.

### 3. BUG-003 [MEDIUM]: Hilangnya `parse_mode="HTML"` pada Perintah Reset Owner
- **File**: [`bot/handlers/commands.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/commands.py)
- **Masalah**: Perintah `/orreset_user` dan `/orreset_agra` mencetak tag HTML mentah seperti `<code>/orreset_user ...</code>` dan `<b>Reset selesai.</b>` tanpa parameter `parse_mode="HTML"`, sehingga tag tampil sebagai plain text bagi pengguna.
- **Solusi**: Menambahkan `parse_mode="HTML"` pada seluruh `update.message.reply_text()` di dalam handler `cmd_orreset_user` dan `cmd_orreset_agra`.

### 4. BUG-004 [MEDIUM]: Proteksi Limit 4096 Karakter pada PM Forwarding
- **File**: [`bot/handlers/messages.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/messages.py)
- **Masalah**: Penerusan pesan privat panjang dari pengguna ke grup petinggi (`PETINGGI_GID`) dapat melebihi batas 4096 karakter Telegram API, menyebabkan `BadRequest: message is too long` dan hilangnya pesan.
- **Solusi**: Menambahkan pengecekan panjang pesan terformat `full_msg = f"{header}:\n\n{text_esc}"`. Jika `len(full_msg) > 4000`, bot memotong pesan secara proporsional dan menyematkan indikator `\n\n<i>... [pesan dipotong]</i>` sebelum memanggil `send_message`.

### 5. BUG-005 [LOW]: Offloading CPU-bound Pillow Rendering ke Worker Thread
- **File**: [`bot/handlers/kartu.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/kartu.py), [`bot/handlers/kontrak.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/kontrak.py)
- **Masalah**: Pembuatan gambar kartu identitas (`render_kic_png_bytes`, `render_kts_png_bytes`) dan dokumen kontrak kerja (`render_kontrak_png_bytes`) memproses grafis Pillow secara sinkron langsung di main asyncio event loop, yang dapat menyebabkan mikro-lag/freezing pada concurrency tinggi.
- **Solusi**: Membungkus eksekusi fungsi rendering grafis menggunakan `await asyncio.to_thread(...)` sehingga berjalan di background thread pool dan tidak memblokir event loop.

### 6. BUG-006 [LOW] & Test Isolation: Kebocoran Koneksi Database & Kontaminasi State Global
- **File**: [`tests/test_deep_qa.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_deep_qa.py), [`tests/test_charyarthi.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_charyarthi.py), [`tests/test_purva.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_purva.py), [`tests/test_chat_command.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_chat_command.py)
- **Masalah**:
  1. Tes-tes membuka koneksi `conn = await db.connect()` tetapi tidak memanggil `await conn.close()` di blok `finally`, menyebabkan socket pool terkuras dan transport SSL aiohttp error saat full test run.
  2. `test_chat_command.py` memutasi konfigurasi global `bot.settings.OWNER_ID = 999` tanpa mengembalikannya di blok `finally`. Hal ini merusak otorisasi admin pada tes-tes setelahnya (khususnya `test_qa_charyarthi_full_e2e_flow`).
- **Solusi**:
  1. Menambahkan `await conn.close()` di setiap blok `finally` pada seluruh file pengujian.
  2. Mengisolasi mutasi `bot.settings.OWNER_ID` dengan pola `old_owner_id = bot.settings.OWNER_ID` dan merestorasinya pada `finally`.

---

## Verifikasi & Hasil QA

Pengujian otomatis dijalankan secara menyeluruh terhadap database Turso pengembangan:
```powershell
python -m pytest tests/
```

### Hasil:
- **58 Passed, 0 Failed** (Durasi: ~9 menit 51 detik)
- Tingkat kelulusan: **100%**
- Tidak ada memory/connection leak, tidak ada event loop warnings, dan integritas isolasi pengujian terjaga sempurna.

