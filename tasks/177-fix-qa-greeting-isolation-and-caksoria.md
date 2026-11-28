# Task 177: Perbaikan Isolasi `OWNER_ID` di `test_greeting.py` & Bug `caksoria`

## Akar Masalah
1. **Test Isolation Leak (`tests/test_greeting.py`)**:
   - Beberapa fungsi pengujian pada `tests/test_greeting.py` menimpa `bot.settings.OWNER_ID = 999` secara langsung tanpa me-restore nilai aslinya.
   - Saat dijalankan dalam satu sesi `pytest` bersama `tests/test_mass_setrole_purna.py`, 3 pengujian owner (`test_security_guards`, `test_command_setrole_purna_all_flow`, `test_command_tutup_generasi_flow`) gagal karena `is_owner(OWNER_ID)` membandingkan `OWNER_ID` awal dengan `999`.
2. **Game Caksoria (`bot/games/caksoria.py` & `tests/test_caksoria.py`)**:
   - `mulai_caksoria` langsung mengakses `update.effective_user.id` tanpa guard `None`, dan `tests/test_caksoria.py::test_caksoria_user_scenario_matching_and_timing` membuat mock `Update` tanpa menyetel `up_start.effective_user`, sehingga `json.dumps(initial_state)` melempar `TypeError: Object of type MagicMock is not JSON serializable`.
   - Selain itu, `job_end_caksoria` belum membersihkan `chat_id` dari cache memori `active_game_chats` saat ronde selesai secara alami (berbeda dengan `berhenti_caksoria` dan `tahan_dulu.py`).

## Perbaikan
- **`tests/test_greeting.py`**: Menambahkan fixture `@pytest.fixture(autouse=True)` `_restore_owner_id()` untuk otomatis mengembalikan `bot.settings.OWNER_ID` setelah setiap tes.
- **`bot/games/caksoria.py`**:
  - Menambahkan guard `update.effective_user.id if update.effective_user else None` pada `started_by`.
  - Membersihkan `chat_id` dari `context.bot_data["active_game_chats"]` pada `job_end_caksoria` setelah sesi diakhiri.
- **`tests/test_caksoria.py`**: Menyediakan `up_start.effective_user = create_mock_user(999, "starter", "Starter")` pada `test_caksoria_user_scenario_matching_and_timing`.

## Verifikasi
- `pyrefly check bot/games/caksoria.py`: **0 errors**.
- Seluruh 20 suite tes offline (termasuk `test_greeting.py` + `test_mass_setrole_purna.py` dalam satu sesi): **162 passed in 21.65s**.
- `pytest tests/test_caksoria.py -v` (Turso dev DB): **3 passed in 31.72s**.
