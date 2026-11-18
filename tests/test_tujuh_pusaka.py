import html
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, MagicMock
import bot.games.tujuh_pusaka as tp


def run_sync(coro):
    """Drive async coroutines synchronously without requiring OS socket pairs."""
    stack = [coro]
    val = None
    exc = None
    while stack:
        top = stack[-1]
        try:
            if exc:
                curr_exc = exc
                exc = None
                res = top.throw(curr_exc)
            else:
                res = top.send(val)
                val = None
            if inspect.iscoroutine(res):
                stack.append(res)
            elif res is None:
                pass
            else:
                val = res
        except StopIteration as e:
            stack.pop()
            val = e.value
        except Exception as e:
            stack.pop()
            exc = e
    if exc:
        raise exc
    return val


class DummyLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


def test_resolve_card_id_default_names():
    # 1. Role keys (rektor, warek1, warek2, sekre1, sekre2, sekre3, pusaka)
    assert tp.resolve_card_id("rektor") == "rektor"
    assert tp.resolve_card_id("warek1") == "warek1"
    assert tp.resolve_card_id("warek 1") == "warek1"
    assert tp.resolve_card_id("warek2") == "warek2"
    assert tp.resolve_card_id("sekre1") == "sekre1"
    assert tp.resolve_card_id("sekre 1") == "sekre1"
    assert tp.resolve_card_id("sekre2") == "sekre2"
    assert tp.resolve_card_id("sekre3") == "sekre3"
    assert tp.resolve_card_id("pusaka") == "pusaka"

    # 2. Legacy name keys (dika, nivia, nuansa, leonie, dyah, neil)
    assert tp.resolve_card_id("dika") == "rektor"
    assert tp.resolve_card_id("nivia") == "warek1"
    assert tp.resolve_card_id("nuansa") == "warek2"
    assert tp.resolve_card_id("leonie") == "sekre1"
    assert tp.resolve_card_id("dyah") == "sekre2"
    assert tp.resolve_card_id("neil") == "sekre3"

    # 3. Case-insensitivity
    assert tp.resolve_card_id("REKTOR") == "rektor"
    assert tp.resolve_card_id("DIKA") == "rektor"
    assert tp.resolve_card_id("Nivia") == "warek1"
    assert tp.resolve_card_id("LeOnIe") == "sekre1"

    # 4. Multi-word display name & stripped 'kartu ' prefix
    assert tp.resolve_card_id("Kartu Pusaka") == "pusaka"
    assert tp.resolve_card_id("kartu pusaka") == "pusaka"
    assert tp.resolve_card_id("pusaka") == "pusaka"

    # 5. Number fallback (1-7)
    assert tp.resolve_card_id("1") == "rektor"
    assert tp.resolve_card_id("2") == "warek1"
    assert tp.resolve_card_id("7") == "pusaka"
    assert tp.resolve_card_id("0") is None
    assert tp.resolve_card_id("8") is None

    # 6. Invalid inputs
    assert tp.resolve_card_id("bukan_kartu") is None
    assert tp.resolve_card_id("") is None
    assert tp.resolve_card_id(None) is None


def test_card_info_contains_names():
    info = tp.get_card_info()
    assert tp.CARDS["rektor"]["name"] in info
    assert tp.CARDS["warek1"]["name"] in info
    assert tp.CARDS["warek2"]["name"] in info
    assert tp.CARDS["sekre1"]["name"] in info
    assert tp.CARDS["sekre2"]["name"] in info
    assert tp.CARDS["sekre3"]["name"] in info
    assert tp.CARDS["pusaka"]["name"] in info


def test_dynamic_rename_support():
    orig_name = tp.NAMA_KARTU["rektor"]
    try:
        # Simulate renaming a card in NAMA_KARTU & CARDS
        new_name = "Bambang"
        tp.NAMA_KARTU["rektor"] = new_name
        tp.CARDS["rektor"]["name"] = new_name

        # Verify resolve_card_id automatically resolves new name
        assert tp.resolve_card_id("bambang") == "rektor"
        assert tp.resolve_card_id("BAMBANG") == "rektor"
        # Role key and legacy key still resolve cleanly
        assert tp.resolve_card_id("rektor") == "rektor"
        assert tp.resolve_card_id("dika") == "rektor"

        # Verify card info reflects new name
        info = tp.get_card_info()
        assert "Bambang" in info
    finally:
        tp.NAMA_KARTU["rektor"] = orig_name
        tp.CARDS["rektor"]["name"] = orig_name


def test_calculate_duel_mechanics():
    # Pusaka vs Pusaka is draw
    res, p_pen, b_pen, desc = tp.calculate_duel("pusaka", "pusaka", 0, 0)
    assert res == "draw"

    # Rektor (Str 90) vs Warek 1 (Str 75)
    # Warek 1 gets +20 vs higher Str (75 + 20 = 95) and cancels Rektor's bonus
    # Rektor has 90 vs Warek 1 (95) -> Warek 1 wins (bot)
    res, p_pen, b_pen, desc = tp.calculate_duel("rektor", "warek1", 0, 0)
    assert res == "bot"
    assert "vs" in desc

    # Legacy key compatibility
    res_legacy, _, _, _ = tp.calculate_duel("dika", "nivia", 0, 0)
    assert res_legacy == "bot"

    # Pusaka reverses normal victory
    # Sekre 3 (60) vs Pusaka (0). Final 60 > 0. Pusaka reverses: player loses -> 'bot'
    res, p_pen, b_pen, desc = tp.calculate_duel("sekre3", "pusaka", 0, 0)
    assert res == "bot"
    assert "[REVERSED]" in desc


def test_proses_pesan_and_pilih_kartu():
    session = {
        "id": 999,
        "chat_id": -10012345,
        "game_name": "tujuh_pusaka",
        "state_json": json.dumps({
            "phase": tp.PHASE_PLAYING,
            "round": 1,
            "started_by": 1001,
            "players": {
                "1001": {
                    "name": "Alice",
                    "cards": list(tp.CARDS.keys()),
                    "wins": 0,
                    "next_round_penalty": 0,
                    "bot_next_round_penalty": 0,
                },
                "1002": {
                    "name": "Bob",
                    "cards": list(tp.CARDS.keys()),
                    "wins": 0,
                    "next_round_penalty": 0,
                    "bot_next_round_penalty": 0,
                }
            },
            "bot_cards": list(tp.CARDS.keys()),
            "choices": {}
        })
    }

    mock_db = MagicMock()
    mock_db.get_active_game_session = AsyncMock(return_value=session)
    mock_db.update_game_session_state = AsyncMock()

    mock_conn = MagicMock()

    # Context setup
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot_data = {"game_locks": {999: DummyLock()}}
    ctx.job_queue = MagicMock()
    ctx.job_queue.get_jobs_by_name = MagicMock(return_value=[])

    # Update setup
    up = MagicMock()
    up.effective_user = MagicMock()
    up.effective_user.id = 1001
    up.effective_user.first_name = "Alice"
    up.message = MagicMock()
    up.message.reply_text = AsyncMock()

    # Test 1: Invalid card choice
    up.message.text = "/pusaka kartu_palsu"
    run_sync(tp.proses_pesan_tujuh_pusaka(up, ctx, mock_db, mock_conn, session))
    up.message.reply_text.assert_called_once()
    assert "bukan kartu yang valid" in up.message.reply_text.call_args[0][0]

    # Test 2: Valid card choice with multi-word "kartu pusaka"
    up.message.reply_text.reset_mock()
    up.message.text = "/pusaka kartu pusaka"
    run_sync(tp.proses_pesan_tujuh_pusaka(up, ctx, mock_db, mock_conn, session))
    mock_db.update_game_session_state.assert_called_once()
    saved_state = mock_db.update_game_session_state.call_args[0][2]
    assert saved_state["choices"]["1001"] == "pusaka"
    assert "Alice telah memilih kartu" in up.message.reply_text.call_args[0][0]


if __name__ == "__main__":
    test_resolve_card_id_default_names()
    test_card_info_contains_names()
    test_dynamic_rename_support()
    test_calculate_duel_mechanics()
    test_proses_pesan_and_pilih_kartu()
    print("ALL 5 TUJUH PUSAKA TESTS PASSED!")
