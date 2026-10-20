# Task 122: Perbaikan Fitur `/pindah_data`, Foreign Key Constraint, dan Sanitasi HTML

## Ringkasan Masalah
Pengguna melaporkan bahwa saat menjalankan perintah `/pindah_data <id_lama|@username_lama> <id_baru|@username_baru>`, bot tidak memberikan respons sama sekali ("gada respon ya, gak berubah jg").

Setelah dilakukan investigasi mendalam dan holistik, ditemukan 3 akar masalah teknis:
1. **Penggunaan Karakter Kurung Siku `< >` & Unescaped HTML Parse Error**:
   - Pengguna menyertakan kurung siku placeholder `< >` atau input karakter khusus yang tidak di-*escape*.
   - Bot menggunakan `ParseMode.HTML` sebagai default. Saat membalas dengan teks `f"User lama {old_query}..."`, Telegram menganggap string `<...>` sebagai tag HTML yang tidak valid / tidak didukung (`unsupported start tag`).
   - Telegram API melempar error `BadRequest: Can't parse entities` yang ditangkap secara diam-diam oleh `error_handler` global di `main.py` tanpa mengirim balasan ke chat. Akibatnya, bot tampak hening (tidak merespons).
2. **Pelanggaran Foreign Key Constraint pada Database (`db.migrate_user_data`)**:
   - Metode `migrate_user_data` sebelumnya langsung menjalankan `UPDATE users SET telegram_id = new_id WHERE telegram_id = old_id`.
   - Karena `users.telegram_id` adalah Primary Key yang direferensikan oleh tabel-tabel anak (`agra_ledger`, `attendance_records`, `task_submissions`, `profile_change_requests`, dll), SQLite/Turso memblokir query tersebut dengan `FOREIGN KEY constraint failed`.
   - Update tabel-tabel anak juga tidak bisa dilakukan sebelum `new_id` ada di tabel `users`. Ini menimbulkan kondisi saling kunci (Catch-22).
3. **Pengecekan Role Owner dan Resolusi Target**:
   - Pengecekan owner sebelumnya hanya mengandalkan kolom database `row["role"] == ROLE_OWNER` tanpa mengecek `is_owner(update.effective_user.id)` dari `.env` (`OWNER_ID` / `ADMIN_IDS`).
   - Resolusi target hanya memakai `get_user_by_username_or_id` dasar tanpa memanfaatkan `resolve_target_user` (yang mendukung pencarian `group_seen_users` dan fallback IPC Userbot `RESOLVE:`).

## Solusi & Perubahan Teknis
1. **Pembersihan Argumen & HTML Escaping (`bot/handlers/commands.py`)**:
   - Argumen `context.args` dibersihkan dari karakter kurung siku: `context.args[0].strip().strip("<>")`.
   - Seluruh variabel dinamis pada string pesan keluar dibungkus menggunakan `html.escape()`.
   - Menambahkan pengecekan wewenang: `if not is_owner(update.effective_user.id) and (not row or row["role"] != ROLE_OWNER):`.
   - Mengintegrasikan fungsi terpusat `resolve_target_user` untuk mengenali username, ID numerik, seen users, serta fallback IPC userbot.
2. **Pola Insert-Update-Delete pada `migrate_user_data` (`bot/database.py`)**:
   - Menggantikan direct `UPDATE users` dengan pola 3 tahap yang aman dari Foreign Key:
     1. `INSERT INTO users (...) SELECT new_id, ... FROM users WHERE telegram_id = old_id`: Memastikan `new_id` sudah ada sebagai parent yang sah di tabel `users`.
     2. `UPDATE [child_tables] SET [user_col] = new_id WHERE [user_col] = old_id`: Mengalihkan seluruh relasi tabel anak (`agra_ledger`, `attendance_sessions`, `attendance_records`, `task_assignments`, `task_submissions`, `profile_change_requests`, `audit_log`, `group_seen_users`, `menfess_history`, `manosraya_history`, `promo_verifications`, `linked_accounts`, `user_chat_stats`, `charyarthi_answers`) ke `new_id`.
     3. `DELETE FROM users WHERE telegram_id = old_id`: Menghapus baris `old_id` setelah tidak ada lagi tabel anak yang mereferensikannya.
   - Memastikan nama dan identitas user baru tidak terhapus jika akun baru belum pernah menjalankan `/start`.
3. **Penambahan Unit Test (`tests/test_pindah_data.py`)**:
   - Memverifikasi eksekusi `migrate_user_data` end-to-end dengan validasi integritas data ledger Agra.
   - Memverifikasi sanitasi kurung siku `< >` pada `cmd_pindah_data` dan memastikan pesan balasan terkirim sukses.
