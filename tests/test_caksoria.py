import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat
from bot.database import Database
import bot.games.caksoria as caksoria
from bot.handlers import games


def create_mock_user(uid: int, username: str, first_name: str):
    u = MagicMock(spec=User)
    u.id = uid
    u.username = username
    u.first_name = first_name
    u.last_name = "User"
    u.language_code = "id"
    u.is_premium = False
    u.is_bot = False
    u.added_to_attachment_menu = None
    u.can_connect_to_business = None
    u.allows_write_to_pm = None
    u.to_dict = MagicMock(return_value={})
    return u


def create_mock_context(db, conn):
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=12345))
    ctx.job_queue = MagicMock()
    ctx.bot_data = {}
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    return ctx


@pytest.mark.asyncio
async def test_caksoria_atur_setting():
    db = Database()
    conn = await db.connect()
    
    try:
        ctx = create_mock_context(db, conn)
        msg = MagicMock(spec=Message)
        msg.reply_text = AsyncMock()
        up = MagicMock(spec=Update)
        up.message = msg
        
        # /atur caksoria testing kata1, kata2, kata3
        await caksoria.atur_caksoria(up, ctx, db, conn, "test_setting", "kata1, kata2, kata3")
        
        setting = await db.get_game_setting(conn, "caksoria", "test_setting")
        assert setting is not None
        assert setting["valid_words"] == ["kata1", "kata2", "kata3"]
        
        msg.reply_text.assert_called_once()
        assert "Setting <b>test_setting</b> untuk Caksoria disimpan" in msg.reply_text.call_args.args[0]
    finally:
        await db.delete_game_setting(conn, "caksoria", "test_setting")
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_caksoria_user_scenario_matching_and_timing():
    """
    Test skenario persis dari permintaan user:
    - Delay 7 detik
    - Keyword: "halo"
    - User zoldy (5.43s, matches keyword) -> 👺 kecepetan
    - User dika (8.18s, matches keyword) -> 🥳 sesuai keyword
    - User cecil (8.25s, no keyword) -> 👺 tidak sesuai format
    - User bena (9.12s, no keyword) -> 👺 tidak sesuai format
    - User abel (32.09s, matches keyword) -> 🥳 sesuai keyword
    - Window penerimaan 30 detik (delay 7s + 30s = 37s)
    """
    db = Database()
    conn = await db.connect()
    chat_id = -1009988776655
    
    try:
        ctx = create_mock_context(db, conn)
        
        # 1. Setup setting
        await db.upsert_game_setting(conn, "caksoria", "kw_test", {"valid_words": ["halo"]})
        await conn.commit()
        
        # 2. Mulai caksoria dengan setting kw_test dan delay 7
        msg_start = MagicMock(spec=Message)
        msg_start.reply_text = AsyncMock()
        up_start = MagicMock(spec=Update)
        up_start.effective_chat = MagicMock(spec=Chat, id=chat_id)
        up_start.message = msg_start
        
        await caksoria.mulai_caksoria(up_start, ctx, db, conn, "kw_test 7")
        
        # Verifikasi job run_once dijadwalkan pada delay 7 + 30 = 37 detik
        ctx.job_queue.run_once.assert_called_once()
        job_call_args = ctx.job_queue.run_once.call_args
        assert job_call_args.args[1] == 37  # 7 + 30 detik
        assert job_call_args.kwargs["name"] == f"caksoria_{chat_id}"
        
        session = await db.get_active_game_session(conn, chat_id)
        assert session is not None
        assert session["game_name"] == "caksoria"
        
        start_time = 1000.0
        # Simulasikan start_time pada state
        state = json.loads(session["state_json"])
        state["start_time"] = start_time
        await db.update_game_session_state(conn, session["id"], state)
        
        # Helper untuk mengirim pesan pada t detik tertentu
        async def send_msg(uid, name, text, elapsed):
            u = create_mock_user(uid, name.lower(), name)
            m = MagicMock(spec=Message)
            m.text = text
            m.caption = None
            up = MagicMock(spec=Update)
            up.effective_user = u
            up.effective_message = m
            
            # Patch time.time()
            from unittest.mock import patch
            with patch("time.time", return_value=start_time + elapsed):
                await caksoria.proses_pesan_caksoria(up, ctx, db, conn, session)
                
        # Kirim 5 pesan sesuai skenario
        await send_msg(101, "zoldy", "halo", 5.43)
        await send_msg(102, "dika", "halo", 8.18)
        await send_msg(103, "cecil", "sembarang kata", 8.25)
        await send_msg(104, "bena", "bukan halo", 9.12)
        await send_msg(105, "abel", "halo", 32.09)
        
        # Kirim pesan kedua dari dika (seharusnya diabaikan karena 1 user cuma dinilai 1x)
        await send_msg(102, "dika", "halo lagi", 15.00)
        
        # Ambil session yang terupdate
        session_updated = await db.get_active_game_session(conn, chat_id)
        state_updated = json.loads(session_updated["state_json"])
        entries = state_updated["entries"]
        
        assert len(entries) == 5  # dika pesan kedua diabaikan
        
        # Cek masing-masing entri
        e_zoldy = next(e for e in entries if e["name"] == "zoldy")
        assert e_zoldy["emoji"] == "👺"
        assert round(e_zoldy["diff"], 2) == 5.43
        
        e_dika = next(e for e in entries if e["name"] == "dika")
        assert e_dika["emoji"] == "🥳"
        assert round(e_dika["diff"], 2) == 8.18
        
        e_cecil = next(e for e in entries if e["name"] == "cecil")
        assert e_cecil["emoji"] == "👺"
        assert round(e_cecil["diff"], 2) == 8.25
        
        e_bena = next(e for e in entries if e["name"] == "bena")
        assert e_bena["emoji"] == "👺"
        assert round(e_bena["diff"], 2) == 9.12
        
        e_abel = next(e for e in entries if e["name"] == "abel")
        assert e_abel["emoji"] == "🥳"
        assert round(e_abel["diff"], 2) == 32.09
        
        # 3. Akhiri game via job_end_caksoria
        mock_job = MagicMock()
        mock_job.chat_id = chat_id
        mock_job.data = {"session_id": session["id"]}
        ctx.job = mock_job
        
        await caksoria.job_end_caksoria(ctx)
        
        # Cek pesan hasil di bot.send_message
        ctx.bot.send_message.assert_called_once()
        sent_text = ctx.bot.send_message.call_args.kwargs["text"]
        
        # Format "emoji + nama + detik" tanpa skor
        assert "👺 zoldy: 5.43s" in sent_text
        assert "🥳 dika: 8.18s" in sent_text
        assert "👺 cecil: 8.25s" in sent_text
        assert "👺 bena: 9.12s" in sent_text
        assert "🥳 abel: 32.09s" in sent_text
        assert "🥳 Sesuai keyword" in sent_text
        assert "👺 Kecepetan / tidak sesuai format" in sent_text
        
        # Verifikasi urutan tercepat ke terlambat
        idx_zoldy = sent_text.find("zoldy")
        idx_dika = sent_text.find("dika")
        idx_cecil = sent_text.find("cecil")
        idx_bena = sent_text.find("bena")
        idx_abel = sent_text.find("abel")
        assert idx_zoldy < idx_dika < idx_cecil < idx_bena < idx_abel
        
        # Verifikasi sesi sudah berakhir di DB
        active_after = await db.get_active_game_session(conn, chat_id)
        assert active_after is None
        
    finally:
        await db.delete_game_setting(conn, "caksoria", "kw_test")
        active = await db.get_active_game_session(conn, chat_id)
        if active:
            await db.end_game_session(conn, active["id"])
        await conn.execute("DELETE FROM game_sessions WHERE chat_id = ?", (chat_id,))
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_caksoria_routing_in_games_handler():
    """Test routing /bermain, /status, /berhenti, /hasil di games.py."""
    assert "caksoria" in games.AVAILABLE_GAMES
    assert games.AVAILABLE_GAMES["caksoria"] == "Caksoria"
