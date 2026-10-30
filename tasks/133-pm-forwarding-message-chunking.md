# Task 133: Message Chunking untuk Penerusan Pesan PM Panjang ke Petinggi

## Ringkasan Eksekutif
Sebelumnya, ketika seorang pengguna mengirim pesan langsung (Private Message) ke bot dengan panjang melebihi 4.000 karakter, bot memotong (*truncate*) pesan tersebut dan menyematkan label `... [pesan dipotong]`. Akibatnya, petinggi kehilangan sisa konteks atau isi pesan yang dituliskan pengguna.

Pembaruan ini mengganti mekanisme pemotongan (*truncate*) dengan **message chunking (pemecahan pesan bersambung)**. Bot kini memecah teks panjang menjadi beberapa bagian (*chunk*) aman (< 3.500 karakter per pesan setelah `html.escape`) dan meneruskannya secara berurutan ke grup petinggi (`PETINGGI_GID`). Bagian lanjutan secara otomatis dikirim sebagai *reply* ke balon pesan pertama sehingga seluruh isi pesan tersampaikan 100% dan terorganisir rapi.

---

## Rincian Perubahan Teknis

### 1. Fungsi Helper `chunk_text_html`
- **File**: [`bot/handlers/messages.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/messages.py)
- **Logika**:
  - Memecah teks baris demi baris (`splitlines(keepends=True)`) dengan batas `max_len = 3500` karakter ter-escape (`html.escape`).
  - Jika terdapat baris yang sangat panjang tanpa karakter *newline*, fungsi akan memotongnya per karakter secara aman sehingga tidak merusak entitas HTML (seperti `&amp;` atau `&lt;`).
  - Mengembalikan daftar potongan string (`list[str]`) yang jika digabungkan kembali sama persis dengan teks asli tanpa ada karakter yang hilang.

### 2. Logika Penerusan di `on_private_message`
- **File**: [`bot/handlers/messages.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/messages.py)
- **Logika**:
  - Jika panjang total pesan terformat (`header` + pesan pengguna) `<= 3900` karakter, pesan dikirim dalam 1 balon pesan tunggal tanpa penanda pecahan `(1/1)`.
  - Jika panjang total pesan terformat `> 3900` karakter:
    1. Pesan dipecah menjadi beberapa chunk menggunakan `chunk_text_html(raw_text, max_len=3500)`.
    2. Chunk pertama dikirim dengan header indeks: `f"{header} (1/{total_chunks}):\n\n{html.escape(chunks[0])}"`.
    3. Setiap chunk lanjutan dikirim dengan penanda indeks dan dikaitkan sebagai balasan (*reply*) ke ID pesan pertama:
       ```python
       cont_text = f"<i>[Lanjutan #ID_{uid} ({idx}/{total_chunks})]:</i>\n\n{html.escape(chunk)}"
       await context.bot.send_message(
           chat_id=PETINGGI_GID,
           text=cont_text,
           parse_mode="HTML",
           disable_web_page_preview=True,
           reply_to_message_id=first_msg.message_id
       )
       ```

---

## Pengujian & Verifikasi

Pengujian otomatis komprehensif ditambahkan pada [`tests/test_messages_chunking.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_messages_chunking.py):
1. `test_chunk_text_html_short`: Memastikan pesan pendek tidak dipecah sembarangan.
2. `test_chunk_text_html_multiline`: Memastikan teks multi-baris panjang dipecah dengan benar pada batas baris dan teks hasil rekombinasi 100% identik dengan teks asli.
3. `test_chunk_text_html_no_newlines`: Memastikan teks sangat panjang tanpa *newline* dipecah secara proporsional.
4. `test_chunk_text_html_html_entities_expansion`: Memastikan karakter khusus seperti `<tag>` dievaluasi panjangnya setelah ekspansi HTML entitas sehingga tidak melanggar batas Telegram.
5. `test_on_private_message_chunking`: Memverifikasi pesan pendek terkirim 1 kali ke petinggi, dan pesan panjang (> 4.000 karakter) dikirim bersambung dengan reply ke pesan pertama.

**Hasil Uji Otomatis:**
```powershell
python -m pytest tests/test_messages_chunking.py -v
```
- Status: **5 passed in 0.65s (100% Pass)**.

