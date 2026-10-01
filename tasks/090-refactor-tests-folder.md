# 090 — Restrukturisasi & Pengelompokan Test Suite ke Folder tests/

## Apa yang Dikerjakan

1. **Pengelompokan File Test**:
   - Memindahkan seluruh file pengujian dan script QA (`test_logic.py`, `test_major_logic.py`, `test_presensi.py`, `test_presensi_ukm.py`, `test_runner.py`, `test_layout.py`, `test_mec.py`, `test_qa_082.py`) dari root direktori proyek ke direktori khusus `tests/`.
   - Membuat file `tests/__init__.py` agar direktori `tests/` terorganisir sebagai Python test package.

2. **Integrasi Pytest Runner**:
   - Menambahkan decorator `@pytest.mark.asyncio` dan wrapper `test_all_commands_runner` di `tests/test_runner.py` agar `pytest` secara otomatis dapat menjalankan pengujian kelengkapan seluruh command handler (43+ command).

3. **Pembaruan Dokumentasi QA**:
   - Memperbarui `docs/qa.md` untuk mencerminkan perintah pengujian standar yang baru: `python -m pytest tests/` atau `pytest`.

## Hasil Pengujian

Menjalankan perintah `python -m pytest`:
- `tests/test_logic.py` — PASSED
- `tests/test_major_logic.py` — PASSED
- `tests/test_presensi.py` — PASSED
- `tests/test_presensi_ukm.py` — PASSED
- `tests/test_runner.py` — PASSED

Total: **5 test suite PASSED 100%** (0 error, 0 failure).
