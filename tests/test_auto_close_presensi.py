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


@pytest.mark.asyncio
async def test_daily_staff_attendance_lifecycle_and_stale_recovery():
    from unittest.mock import AsyncMock, MagicMock
    from bot.jobs import daily_staff_attendance_open, daily_staff_attendance_close
    from bot.handlers.attendance import _record_hadir
    from bot.settings import OWNER_ID

    db = Database()
    conn = await db.connect()

    # Pastikan test owner ada di database
    owner_id = OWNER_ID or 999111
    await db.upsert_user_from_telegram(
        conn,
        telegram_id=owner_id,
        username="test_daily_staff_owner",
        first_name="Test",
        last_name="Owner",
        language_code="id",
        is_premium=False,
        is_bot=False,
        raw_profile={},
    )
    await db.set_role(conn, owner_id, "owner")

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    mock_msg = MagicMock()
    mock_msg.message_id = 77777
    context.bot.send_message = AsyncMock(return_value=mock_msg)
    context.bot.edit_message_text = AsyncMock()

    created_sids = []
    try:
        # 1. Buka sesi via cron (opened_by=None)
        sid1 = await daily_staff_attendance_open(context, opened_by=None)
        assert sid1 is not None
        created_sids.append(sid1)

        sess1 = await db.get_attendance_session(conn, sid1)
        assert sess1 is not None
        assert sess1["class_id"] == "staff_auto"
        assert sess1["closed_at"] is None
        assert sess1["opened_by"] != 0  # Harus user nyata, bukan 0

        # 2. Verifikasi Owner bisa mencatat kehadiran di staff_auto tanpa terblokir self-attendance guard
        ok, msg, _ = await _record_hadir(
            db, conn, sid1, owner_id, "owner", ["staff_auto"], status="hadir"
        )
        assert ok is True
        assert "berhasil" in msg.lower() or "tercatat" in msg.lower()

        # 3. Panggilan ulang saat sesi masih segar (< 16 jam) harus mengembalikan sesi yang sama
        sid1_repeat = await daily_staff_attendance_open(context, opened_by=None)
        assert sid1_repeat == sid1

        # 4. Simulasikan sesi basi (stale) dari hari sebelumnya (> 16 jam lalu)
        now = time.time()
        await conn.execute("UPDATE attendance_sessions SET opened_at = ? WHERE id = ?", (now - (17 * 3600), sid1))
        await conn.commit()

        # Buka sesi berikutnya di hari baru -> sesi lama harus otomatis ditutup dan sesi baru dibuka
        sid2 = await daily_staff_attendance_open(context, opened_by=None)
        assert sid2 is not None
        assert sid2 != sid1
        created_sids.append(sid2)

        # Sesi lama harus sudah ditutup
        sess1_after = await db.get_attendance_session(conn, sid1)
        assert sess1_after["closed_at"] is not None

        # Sesi baru harus berstatus aktif
        sess2 = await db.get_attendance_session(conn, sid2)
        assert sess2["closed_at"] is None

        # 5. Tutup sesi via cron harian
        await daily_staff_attendance_close(context)
        sess2_closed = await db.get_attendance_session(conn, sid2)
        assert sess2_closed["closed_at"] is not None
    finally:
        for sid in created_sids:
            await conn.execute("DELETE FROM attendance_records WHERE session_id = ?", (sid,))
            await conn.execute("DELETE FROM attendance_sessions WHERE id = ?", (sid,))
        await conn.commit()
        await conn.close()


