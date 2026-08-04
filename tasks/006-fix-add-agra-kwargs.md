# Task 006: Memperbaiki Argumen add_agra di menfess.py

## Deskripsi Pekerjaan
1. Memperbaiki pemanggilan fungsi `add_agra` di dalam `menfess.py` yang sebelumnya mengalami `TypeError` karena penggunaan *keyword argument* yang tidak sesuai (`target_telegram_id`).

## Alasan (Why)
- Definisi fungsi `add_agra` di `database.py` menggunakan argumen `target_id`, `actor_id`, `chat_id`, dan `message_id`. Pemanggilan sebelumnya menggunakan nama argumen lama yang sudah diganti (`target_telegram_id` dsb.), sehingga menyebabkan *crash* pada saat pemotongan saldo menfess atau pemberian _gift_.

## Alur Implementasi
1. Mengubah `target_telegram_id` menjadi `target_id`.
2. Mengubah `actor_telegram_id` menjadi `actor_id`.
3. Menambahkan pengisian parameter `chat_id` dan `message_id` yang dibutuhkan oleh `database.py` dengan mengambilnya dari objek `update.effective_chat` dan `update.effective_message`.
