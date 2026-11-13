# Task 136: Rename Role Alumni dari "purva" ke "purna"

## Ringkasan
Mengganti nama role alumni dari `purva` (Purvashishya) menjadi `purna` (Purnata) di seluruh codebase, konfigurasi, tes, dan dokumentasi.

## Perubahan

### 1. Core Constants (`bot/database.py`)
- Konstanta: `ROLE_PURVA = "purva"` → `ROLE_PURNA = "purna"`
- `ROLES_ORDER` diperbarui untuk menggunakan `ROLE_PURNA`
- Logic SKS banking di `set_role()` diperbarui dari `ROLE_PURVA` → `ROLE_PURNA`

### 2. UI Label (`bot/handlers/common.py`)
- Import: `ROLE_PURVA` → `ROLE_PURNA`
- `role_display()`: label `"Purvashishya"` → `"Purnata"`
- `profile_display_keys()`: referensi role diperbarui

### 3. Command Handlers (`bot/handlers/commands.py`)
- Import diperbarui
- `/daftar purva` → `/daftar purna` (menu & handler)
- `/setrole`: error message menyebut `purna` bukan `purva`
- `/agratop purva` → `/agratop purna`
- Scope filtering untuk dosen/dekan diperbarui

### 4. Config (`config/profile_fields.yaml`)
- Field `muse` & `birth_date`: roles list `purva` → `purna`

### 5. Tests
- `tests/test_purva.py`: import & nama fungsi diperbarui
- `tests/test_qa_fixes.py`: semua referensi purva → purna
- `tests/test_charyarthi.py`: import diperbarui
- `tests/test_deep_qa.py`: import diperbarui
- `tests/test_full_system_production_qa.py`: import diperbarui

### 6. Dokumentasi
- `docs/architecture.md`: deskripsi SKS banking diperbarui
- `docs/commands.md`: filter `/daftar` & `/laporan` diperbarui

### 7. Database Migration
- Script `migrate_purva_to_purna.py` dibuat untuk mengubah `role = 'purva'` → `role = 'purna'` di tabel `users` pada Turso DB.
- **Status**: Belum dijalankan karena Turso DB dev saat ini terblokir (kuota reads). Perlu dijalankan saat DB kembali aktif.

## Dampak
- Perintah user: `/daftar purna`, `/agratop purna`, `/setrole purna`
- Tampilan role di profil: "Purnata"
- Data existing di DB perlu dimigrasi (script sudah tersedia)

