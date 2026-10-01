# 089 — Perbaikan Bug Hasil QA Deep Production Audit

## Apa yang Dikerjakan

Memperbaiki bug dan temuan keamanan yang diidentifikasi pada laporan QA `088-qa-deep-production-audit.md`:

1. **Security Fix (`/reload` dan `/pull`)**:
   - Membatasi akses `/reload` dan `/pull` di `bot/handlers/commands.py` hanya untuk `ROLE_OWNER` (`is_owner`). Menghapus akses `ROLE_ADMIN` yang sebelumnya berpotensi menyalahgunakan `os.system` dan `subprocess.run`.

2. **Database & Atomicity (`deduct_agra_if_sufficient`)**:
   - Memperbaiki pengujian `rowcount` di `bot/database.py` pada method `deduct_agra_if_sufficient` agar tidak terjebak menggunakan `lastrowid` lama jika `rowcount` tidak diset oleh driver `libsql_client`.

3. **SQL Query Parameterization**:
   - Memperbaiki f-string `LIMIT {limit + 1} OFFSET {offset}` di `ATT_SESSION` scope pagination di `bot/handlers/commands.py` menjadi query bertipe parameter `LIMIT ? OFFSET ?`.

4. **Memory Leak Fix (`RATE_LIMIT_CACHE`)**:
   - Menambahkan mekanisme pembersihan otomatis (eviction) untuk entri rate limit lama (>60s) di `bot/handlers/common.py` saat cache melebihi 500 entri.

5. **Test Fix (`test_presensi_ukm.py`)**:
   - Menambahkan decorator `@pytest.mark.asyncio` dan merename fungsi tes menjadi `test_presensi_ukm` sehingga `pytest` dapat menemukan dan menjalankan seluruh 4 file tes otomatis dengan sukses (100% PASS).

6. **Dokumentasi Negative Agra Amount (`/add`)**:
   - Menambahkan komentar pada `cmd_add` di `bot/handlers/commands.py` bahwa nominal negatif sengaja diizinkan untuk pengurangan agra / penalti oleh admin/owner/bem.

## Alur Teknis

1. `bot/handlers/commands.py`:
   - `cmd_reload` dan `cmd_pull`: Ganti `row["role"] not in (ROLE_OWNER, ROLE_ADMIN)` menjadi `row["role"] != ROLE_OWNER and not is_owner(...)`.
   - `cmd_add`: Tambahkan inline comment penjelasan penalti agra negatif.
   - `ATT_SESSION`: Mengganti f-string SQL dengan `(limit + 1, offset)` tuple.

2. `bot/database.py`:
   - `deduct_agra_if_sufficient`: Mengecek `rowcount` / `rows_affected` secara ketat tanpa fallback ke `lastrowid`.

3. `bot/handlers/common.py`:
   - `rate_limit_check`: Tambahkan pembersihan dictionary jika `len(RATE_LIMIT_CACHE) > 500`.

4. `test_presensi_ukm.py`:
   - Tambah `import pytest`, `@pytest.mark.asyncio`, dan ganti `async def test():` -> `async def test_presensi_ukm():`.
