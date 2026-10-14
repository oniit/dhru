# Task 099: Perbaikan Missing Import `ROLE_PURVA` pada `cmd_setrole`

## Deskripsi Singkat
Memperbaiki error runtime `NameError: name 'ROLE_PURVA' is not defined` saat admin/owner mengeksekusi perintah `/setrole`.

## Masalah & Analisis
- Pada fungsi [`cmd_setrole`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/commands.py#L3653), terdapat validasi pengecekan role:
  ```python
  if role not in (
      ROLE_OWNER,
      ROLE_ADMIN,
      ROLE_INTERNAL,
      ROLE_BEM,
      ROLE_STUDENT,
      ROLE_PURVA,
      ROLE_MABA,
      ROLE_PUBLIC,
  ):
  ```
- Namun, pada bagian import di awal file `bot/handlers/commands.py`, konstanta `ROLE_PURVA` belum diimpor dari `bot.database`.
- Akibatnya, setiap kali `/setrole` dijalankan, bot mengalami unhandled exception `NameError`.

## Solusi
- Menambahkan import `ROLE_PURVA` dari `bot.database` di bagian atas [`bot/handlers/commands.py`](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/handlers/commands.py#L25).
- Menjalankan AST scan menyeluruh untuk memastikan tidak ada konstanta `ROLE_*` lain yang lupa diimpor di seluruh codebase.
