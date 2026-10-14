import time
import pytest
from bot.database import Database

@pytest.mark.asyncio
async def test_auto_close_stale_sessions():
    db = Database()
    conn = await db.connect()
    
    # Setup test owner
    test_owner_id = 999111
    await db.upsert_user_from_telegram(
        conn,
        telegram_id=test_owner_id,
        username="test_auto_close_owner",
        first_name="Test",
        last_name="Owner",
        language_code="id",
        is_premium=False,
        is_bot=False,
        raw_profile={},
    )
    await db.set_role(conn, test_owner_id, "owner")

    now = time.time()
    
    # 1. Stale manual session (> 2 hours ago)
    sid_stale = await db.open_attendance_session(
        conn, class_id="sm_test", title="Test Stale", opened_by=test_owner_id, chat_id=-100
    )
    await conn.execute("UPDATE attendance_sessions SET opened_at = ? WHERE id = ?", (now - 8000, sid_stale))
    await conn.commit()

    # 2. Stale staff_auto session (> 2 hours ago, but must NOT be auto-closed by this job)
    sid_staff_auto = await db.open_attendance_session(
        conn, class_id="staff_auto", title="Test Staff Auto", opened_by=test_owner_id, chat_id=-100
    )
    await conn.execute("UPDATE attendance_sessions SET opened_at = ? WHERE id = ?", (now - 8000, sid_staff_auto))
    await conn.commit()

    # 3. Fresh manual session (< 2 hours ago)
    sid_fresh = await db.open_attendance_session(
        conn, class_id="sf_test", title="Test Fresh", opened_by=test_owner_id, chat_id=-100
    )
    await conn.execute("UPDATE attendance_sessions SET opened_at = ? WHERE id = ?", (now - 500, sid_fresh))
    await conn.commit()

    try:
        # Run auto close
        closed_ids = await db.auto_close_stale_sessions(conn)
        
        # Verify stale session is closed
        assert sid_stale in closed_ids
        sess_stale = await db.get_attendance_session(conn, sid_stale)
        assert sess_stale["closed_at"] is not None
        assert abs(sess_stale["closed_at"] - (sess_stale["opened_at"] + 7200)) < 1.0

        # Verify staff_auto is NOT closed
        assert sid_staff_auto not in closed_ids
        sess_staff = await db.get_attendance_session(conn, sid_staff_auto)
        assert sess_staff["closed_at"] is None

        # Verify fresh session is NOT closed
        assert sid_fresh not in closed_ids
        sess_fresh = await db.get_attendance_session(conn, sid_fresh)
        assert sess_fresh["closed_at"] is None

    finally:
        # Cleanup test sessions
        await conn.execute(
            "DELETE FROM attendance_sessions WHERE id IN (?, ?, ?)",
            (sid_stale, sid_staff_auto, sid_fresh),
        )
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_periodic_auto_close_attendance_job():
    from unittest.mock import AsyncMock, MagicMock
    from bot.jobs import periodic_auto_close_attendance

    db = Database()
    conn = await db.connect()

    test_owner_id = 999111
    now = time.time()

    sid = await db.open_attendance_session(
        conn, class_id="bem_manual", title="Test BEM", opened_by=test_owner_id, chat_id=-100
    )
    await db.set_attendance_announce_message(conn, sid, 8888)
    await conn.execute("UPDATE attendance_sessions SET opened_at = ? WHERE id = ?", (now - 8000, sid))
    await conn.commit()

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot.edit_message_text = AsyncMock()

    try:
        await periodic_auto_close_attendance(context)

        # Verify session closed
        sess = await db.get_attendance_session(conn, sid)
        assert sess["closed_at"] is not None

        # Verify edit_message_text called with reply_markup=None (buttons removed!)
        assert context.bot.edit_message_text.called
        kwargs = context.bot.edit_message_text.call_args.kwargs
        assert kwargs["chat_id"] == -100
        assert kwargs["message_id"] == 8888
        assert kwargs["reply_markup"] is None
        assert "Sesi ditutup." in kwargs["text"]
    finally:
        await conn.execute("DELETE FROM attendance_sessions WHERE id = ?", (sid,))
        await conn.commit()
        await conn.close()

