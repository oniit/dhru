"""
Deep QA Test & Regression Suite: All about /pfp & Keep -> Poster (@DhruvaPoster).
- Executes real handlers, DB methods, JobQueue, and checker IPC against isolated SQLite + mocks.
- Verifies fixes for BUG-01..BUG-10, KEEP_TO_POST IPC delegation (database is locked fix),
  and process_broadcast_queue UnboundLocalError fix.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from telegram.error import RetryAfter
from telegram.ext import Application

import bot.handlers.pfp as pfp
from bot.database import (
    AiosqliteRowMock,
    Database,
    ROLE_ADMIN,
    ROLE_CHARYARTHI,
    ROLE_INTERNAL,
    ROLE_OWNER,
    ROLE_PUBLIC,
    ROLE_PURNA,
    ROLE_STUDENT,
    SCHEMA,
)
from bot.handlers.commands import help_for_role
from bot.jobs import (
    _format_keep_kloter_owner_report,
    daily_keep_to_post,
    execute_keep_to_post,
    get_keep_forward_lock,
    is_keep_msg_excluded,
    setup_jobs,
)
from bot.timefmt import TZ, get_today_wib


def _make_full_sqlite_conn(enable_fk: bool = True, return_dict: bool = False):
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    if enable_fk:
        raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(SCHEMA)

    class _Cur:
        def __init__(self, cur):
            self._cur = cur
            self.lastrowid = cur.lastrowid
            self.rowcount = cur.rowcount

        async def fetchone(self):
            r = self._cur.fetchone()
            if r is None:
                return None
            return dict(r) if return_dict else r

        async def fetchall(self):
            rows = self._cur.fetchall()
            return [dict(r) for r in rows] if return_dict else rows

    class _Conn:
        def __init__(self):
            self.committed = True

        async def execute(self, sql, params=()):
            cur = raw.execute(sql, params)
            self.committed = False
            return _Cur(cur)

        async def executescript(self, script):
            raw.executescript(script)
            self.committed = True

        async def commit(self):
            raw.commit()
            self.committed = True

        async def close(self):
            raw.close()

    return _Conn(), raw


# =============================================================================
# 1. REAL JOBQUEUE SCHEDULING & WIB TIMING VERIFICATION
# =============================================================================


@pytest.mark.asyncio
async def test_qa_real_jobqueue_computes_exact_wib_next_runs():
    app = Application.builder().token("123456:TESTTOKEN").build()
    with patch("bot.settings.KEEP_CH_ID", -100111), patch("bot.settings.POST_CH_ID", -100222):
        setup_jobs(app)
    await app.job_queue.start()
    try:
        jobs = {j.name: j for j in app.job_queue.jobs() if j.name and "keep_to_post" in j.name}
        assert set(jobs.keys()) == {"keep_to_post_1500", "keep_to_post_1759"}
        wib = ZoneInfo("Asia/Jakarta")
        t15 = jobs["keep_to_post_1500"].next_t.astimezone(wib)
        t17 = jobs["keep_to_post_1759"].next_t.astimezone(wib)
        assert (t15.hour, t15.minute, t15.second) == (15, 0, 0)
        assert (t17.hour, t17.minute, t17.second) == (17, 59, 0)
        assert jobs["keep_to_post_1500"].data == {"kloter_label": "15:00 WIB"}
        assert jobs["keep_to_post_1759"].data == {"kloter_label": "17:59 WIB"}
    finally:
        await app.job_queue.stop()


def test_qa_setup_jobs_skipped_when_channel_env_missing():
    app = MagicMock()
    app.job_queue = MagicMock()
    with patch("bot.settings.KEEP_CH_ID", None), patch("bot.settings.POST_CH_ID", -100222), patch("bot.jobs.PRESENCE_CH_ID", None):
        setup_jobs(app)
    names = [c[1].get("name") for c in app.job_queue.run_daily.call_args_list]
    assert "keep_to_post_1500" not in names
    assert "keep_to_post_1759" not in names


# =============================================================================
# 2. REPRODUCIBLE BUGS — PARSING & INPUT HANDLING
# =============================================================================


def test_fix_bug01_multi_link_and_topic_link_parsing():
    """
    BUG-01 FIX: Strict anchored regex parses topic links cleanly, rejects trailing garbage,
    splits unspaced hyphens into RANGE, and rejects multi-link input without 'to' as INVALID.
    """
    # Two links separated by space without 'to' -> INVALID (must not silently drop 2nd link)
    mode_space, _ = pfp.parse_pfp_args(["https://t.me/ch/100", "https://t.me/ch/120"])
    assert mode_space == "INVALID"

    # Unspaced hyphen: link1-link2 -> cleanly parsed as RANGE
    mode_hyph, data_hyph = pfp.parse_pfp_args(["https://t.me/ch/100-https://t.me/ch/120"])
    assert mode_hyph == "RANGE"
    assert data_hyph == ("https://t.me/ch/100", "https://t.me/ch/120")

    # Trailing garbage characters in message id: /ch/12abc -> rejected
    assert pfp.parse_telegram_post_link("https://t.me/ch/12abc") is None

    # Forum topic link t.me/c/<chat_id>/<topic_id>/<msg_id> -> captures msg_id (123), not topic_id (5)
    assert pfp.parse_telegram_post_link("https://t.me/c/123456789/5/123") == (-100123456789, 123)


# =============================================================================
# 3. REGRESSION FIXES — ABUSE, SECURITY, AND AGRA ECONOMY INTEGRITY
# =============================================================================


@pytest.mark.asyncio
async def test_fix_bug02_blocks_self_loop_and_duplicate_kloter_links():
    """
    BUG-02 FIX: cmd_pfp blocks self-loop forwarding from KEEP_CH_ID/POST_CH_ID/@DhruvaPoster
    and blocks duplicate identical links within the active kloter.
    """
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    await db.upsert_user_from_telegram(
        conn,
        telegram_id=7001,
        username="spampub",
        first_name="Spam",
        last_name=None,
        language_code="id",
        is_premium=False,
        is_bot=False,
        raw_profile={},
    )
    # 1) Self-loop on @DhruvaPoster is rejected cleanly before forwarding
    up_loop = MagicMock()
    up_loop.effective_user.id = 7001
    up_loop.effective_chat.id = 7001
    up_loop.effective_message.reply_text = AsyncMock()
    ctx_loop = MagicMock()
    ctx_loop.args = ["https://t.me/DhruvaPoster/10"]
    ctx_loop.bot.forward_message = AsyncMock(return_value=MagicMock())
    ctx_loop.application.bot_data = {"db": db, "conn": conn}
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_loop, ctx_loop)

    assert ctx_loop.bot.forward_message.await_count == 0
    assert "@DhruvaPoster" in up_loop.effective_message.reply_text.call_args[0][0]
    assert await db.agra_total(conn, 7001) == 0

    # 2) Same normal post submitted 3 times in active kloter -> only 1st succeeds & grants 1 Agra
    replies = []
    for _ in range(3):
        up = MagicMock()
        up.effective_user.id = 7001
        up.effective_chat.id = 7001
        status = AsyncMock()
        up.effective_message.reply_text = AsyncMock(return_value=status)
        ctx = MagicMock()
        ctx.args = ["https://t.me/NormalChannel/10"]
        ctx.bot.forward_message = AsyncMock(return_value=MagicMock())
        ctx.application.bot_data = {"db": db, "conn": conn}
        with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
            await pfp.cmd_pfp(up, ctx)
        replies.append(up.effective_message.reply_text.call_args[0][0])

    assert await db.agra_total(conn, 7001) == 1
    assert "sudah pernah Anda forward" in replies[1]
    assert "sudah pernah Anda forward" in replies[2]
    await conn.close()


@pytest.mark.asyncio
async def test_fix_bug04_unregistered_user_fk_failure_warns_instead_of_claiming_agra():
    """
    BUG-04 FIX: When user hasn't done /start (missing from `users` table) with foreign_keys=ON,
    add_agra raises IntegrityError; bot must NOT falsely tell user '(+1 Agra)'!
    """
    conn, raw = _make_full_sqlite_conn(enable_fk=True)
    db = Database()

    up = MagicMock()
    up.effective_user.id = 999888777  # Not registered in users table
    up.effective_chat.id = -100555
    status = AsyncMock()
    up.effective_message.reply_text = AsyncMock(return_value=status)
    ctx = MagicMock()
    ctx.args = ["https://t.me/pubch/55"]
    ctx.bot.forward_message = AsyncMock(return_value=MagicMock())
    ctx.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up, ctx)

    bal = await db.agra_total(conn, 999888777)
    assert bal == 0
    reply = status.edit_text.call_args[0][0]
    assert "+1 Agra" not in reply
    assert "Poin Agra gagal dicatat" in reply
    await conn.close()


@pytest.mark.asyncio
async def test_qa_security_authorization_matrix_for_post_keep_and_pfp_menus():
    """Verify strict authorization across all roles on /post_keep, /pfp daily/weekly, and cb_pfp."""
    conn, raw = _make_full_sqlite_conn()
    db = Database()

    async def seed(uid, role, prof):
        await conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, f"u{uid}", f"User{uid}", role, json.dumps(prof), 1.0, 1.0),
        )
        await conn.commit()

    await seed(1, ROLE_PUBLIC, {})
    await seed(2, ROLE_STUDENT, {})
    await seed(3, ROLE_CHARYARTHI, {"position_detail": ["d_pfp"]})  # Applicant for PFP, NOT internal yet!
    await seed(4, ROLE_PURNA, {"position_detail": ["d_pfp"]})       # Alumni former PFP!
    await seed(5, ROLE_INTERNAL, {"position_detail": ["d_hrd"]})    # Non-PFP internal staff
    await seed(6, ROLE_INTERNAL, {"position_detail": ["d_pfp"]})    # Valid PFP staff (list)
    await seed(7, ROLE_INTERNAL, {"position_detail": "d_pfp"})      # Valid PFP staff (legacy string)
    await seed(8, ROLE_ADMIN, {})                                   # Admin
    await seed(9, ROLE_OWNER, {})                                   # Owner in DB

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        assert await pfp.is_authorized_pfp_admin(conn, db, 1) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, 2) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, 3) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, 4) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, 5) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, 6) is True
        assert await pfp.is_authorized_pfp_admin(conn, db, 7) is True
        assert await pfp.is_authorized_pfp_admin(conn, db, 8) is True
        assert await pfp.is_authorized_pfp_admin(conn, db, 9) is True

        # Non-owner (even PFP staff #6) MUST NOT access /pfp daily or /pfp weekly or callback pfp:daily
        up = MagicMock()
        up.effective_user.id = 6
        up.effective_message.reply_text = AsyncMock()
        ctx = MagicMock()
        ctx.application.bot_data = {"db": db, "conn": conn}
        for sub in ("daily", "weekly"):
            up.effective_message.reply_text.reset_mock()
            ctx.args = [sub]
            await pfp.cmd_pfp(up, ctx)
            assert "owner" in up.effective_message.reply_text.call_args[0][0].lower()

        up_cb = MagicMock()
        up_cb.effective_user.id = 6
        up_cb.callback_query.answer = AsyncMock()
        for cdata in ("pfp:daily", "pfp:weekly", "pfp:menu"):
            up_cb.callback_query.answer.reset_mock()
            up_cb.callback_query.data = cdata
            await pfp.cb_pfp(up_cb, ctx)
            assert "Hanya owner" in up_cb.callback_query.answer.call_args[0][0]

        # Non-dict JSON / empty profile_json should fail closed safely without crashing
        await conn.execute("UPDATE users SET profile_json = '[]' WHERE telegram_id = 6")
        await conn.commit()
        assert await pfp.is_authorized_pfp_admin(conn, db, 6) is False

    await conn.close()


# =============================================================================
# 4. REPRODUCIBLE BUGS — KEEP -> POSTER FORWARDER, DATA LOSS & RACES
# =============================================================================


@pytest.mark.asyncio
async def test_fix_bug03_keep_last_fwd_id_does_not_skip_middle_failed_message():
    """
    BUG-03 FIX: If message 102 fails while [101, 103] succeed, safe_last_fwd_id is capped at 101
    (< min(failed_ids)=102) so Run 2 still scans and retries 102 without skipping it forever.
    """
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    bot = MagicMock()
    bot.send_message = AsyncMock()

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.delete_messages = AsyncMock(return_value=2)

    async def fake_fwd(chat_id, from_chat_id, message_ids):
        if message_ids == [101, 102, 103]:
            raise Exception("Batch failed")
        if message_ids == [102]:
            raise Exception("Transient timeout on 102")
        return [MagicMock()]

    mock_app.forward_messages = AsyncMock(side_effect=fake_fwd)

    def make_msg(mid):
        m = MagicMock()
        m.id = mid
        m.empty = False
        m.service = False
        m.from_user = None
        m.text = f"Post {mid}"
        return m

    async def hist_run1(_):
        for mid in (103, 102, 101):
            yield make_msg(mid)

    async def hist_run2(_):
        # 101 & 103 were deleted; 102 is STILL in KEEP!
        yield make_msg(102)

    mock_app.get_chat_history.side_effect = [hist_run1(None), hist_run2(None)]

    with patch.dict(os.environ, {"USERBOT_SESSION": "test_session"}), \
         patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC"), \
         patch("bot.settings.OWNER_ID", 999), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("pyrogram.Client", return_value=mock_app):

        c1, err1 = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999)
        assert c1 == 2 and err1 is None
        assert await db.get_setting(conn, "keep_last_fwd_id") == "101"

        # Second run retries 102 cleanly without re-sending 101 or 103
        mock_app.forward_messages = AsyncMock(return_value=[MagicMock()])
        c2, err2 = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999)
        assert c2 == 1 and err2 is None
        assert await db.get_setting(conn, "keep_last_fwd_id") == "102"

    await conn.close()


@pytest.mark.asyncio
async def test_fix_bug06_auto_kloter_waits_for_manual_lock_release():
    """
    BUG-06 FIX: If manual /post_keep holds lock briefly when 15:00 WIB auto kloter triggers,
    daily_keep_to_post awaits lock release (up to 120s) and succeeds cleanly instead of failing.
    """
    lock = get_keep_forward_lock()
    ctx = MagicMock()
    ctx.application.bot_data = {"db": AsyncMock(), "conn": MagicMock()}
    ctx.application.bot_data["db"].get_setting.return_value = "0"
    ctx.application.bot_data["db"].get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}
    ctx.bot.send_message = AsyncMock()
    ctx.job.name = "keep_to_post_1500"
    ctx.job.data = {"kloter_label": "15:00 WIB"}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()

    async def empty_hist(_):
        if False:
            yield None

    mock_app.get_chat_history.side_effect = empty_hist

    await lock.acquire()

    async def release_soon():
        await asyncio.sleep(0.03)
        lock.release()

    releaser = asyncio.create_task(release_soon())
    try:
        with patch.dict(os.environ, {"USERBOT_SESSION": "test_session"}), \
             patch("bot.settings.KEEP_CH_ID", -100111), \
             patch("bot.settings.POST_CH_ID", -100222), \
             patch("bot.settings.API_ID", "12345"), \
             patch("bot.settings.API_HASH", "abcdef"), \
             patch("bot.settings.OWNER_ID", 999), \
             patch("bot.jobs._resolve_owner_chat_id", AsyncMock(return_value=999)), \
             patch("pyrogram.Client", return_value=mock_app):
            await daily_keep_to_post(ctx)
    finally:
        await releaser

    ctx.bot.send_message.assert_called_once()
    msg_text = ctx.bot.send_message.call_args[1]["text"]
    assert "Laporan Kloter" in msg_text
    assert "Gagal" not in msg_text


@pytest.mark.asyncio
async def test_fix_bug08_bot_api_retry_after_sleeps_and_retries_single_post():
    """
    BUG-08 FIX: In forward_posts_to_keep range fallback, RetryAfter (429) sleeps retry_after
    and retries once so valid post 2 is forwarded rather than dropped.
    """
    bot = MagicMock()
    bot.forward_messages = AsyncMock(side_effect=Exception("Batch failed (msg 2 rate limited)"))
    bot.forward_message = AsyncMock(
        side_effect=[MagicMock(), RetryAfter(1), MagicMock(), MagicMock()]
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        count, err = await pfp.forward_posts_to_keep(bot, None, None, -100111, "@ch", 1, 3)

    assert count == 3
    assert err is None
    assert bot.forward_message.await_count == 4
    sleep_mock.assert_any_await(2)


@pytest.mark.asyncio
async def test_fix_bug09_promo_post_mentioning_dhruvaposter_not_excluded():
    """
    BUG-09 FIX: Promo post saying 'cek @DhruvaPoster ya!' is NOT treated as bot error notification.
    """
    m = MagicMock()
    m.empty = False
    m.service = False
    m.from_user = None
    m.text = "Ayo ikuti event terbaru! Info lengkap cek @DhruvaPoster ya!"
    m.caption = None
    assert is_keep_msg_excluded(m, bot_id=123456) is False

    m_summary = MagicMock()
    m_summary.empty = False
    m_summary.service = False
    m_summary.from_user = None
    m_summary.text = "Ringkasan selesai. Silakan cek @DhruvaPoster, ada update!"
    m_summary.caption = None
    assert is_keep_msg_excluded(m_summary, bot_id=123456) is True


# =============================================================================
# 5. REGRESSION FIXES — IPC & DATABASE INTERACTION
# =============================================================================


@pytest.mark.asyncio
async def test_fix_bug05_ipc_commits_and_reads_sqlite_row_cleanly():
    """
    BUG-05 FIX:
    1) create_userbot_request commits transaction cleanly.
    2) _forward_via_userbot_ipc safely reads status & result from raw sqlite3.Row without .get().
    """
    conn, raw = _make_full_sqlite_conn(return_dict=False)
    db = Database()

    req_id = await db.create_userbot_request(conn, "0", "FORWARD:@priv:1:1")
    assert conn.committed is True

    await conn.execute(
        "UPDATE userbot_requests SET status = 'DONE', result = ? WHERE id = ?",
        (json.dumps({"forwarded": 1}), req_id),
    )
    await conn.commit()

    row = await db.get_userbot_request(conn, req_id)
    assert isinstance(row, sqlite3.Row)
    assert not hasattr(row, "get")

    real_sleep = asyncio.sleep

    async def fast_sleep(_):
        await real_sleep(0.02)

    async def complete_pending_req():
        await real_sleep(0.01)
        await conn.execute(
            "UPDATE userbot_requests SET status = 'DONE', result = ? WHERE status = 'PENDING'",
            (json.dumps({"forwarded": 1}),),
        )
        await conn.commit()

    worker = asyncio.create_task(complete_pending_req())
    with patch("asyncio.sleep", new=fast_sleep):
        fwd = await pfp._forward_via_userbot_ipc(conn, db, "@priv", 1, 1, timeout=3.0)
    await worker
    assert fwd == 1
    await conn.close()


@pytest.mark.asyncio
async def test_fix_bug10_migrate_user_data_migrates_pfp_logs():
    """
    BUG-10 FIX: migrate_user_data (/pindah_data) migrates pfp_logs.user_id to new_id
    so daily/weekly stats preserve user join cleanly.
    """
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    await conn.execute(
        "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) VALUES (111, 'old_u', 'OldUser', 'student', '{}', 1.0, 1.0)"
    )
    now = time.time()
    await db.log_pfp_forward(conn, 111, 111, "@ch", 1, 5, 5, now)
    assert await db.migrate_user_data(conn, 111, 222) is True

    cur = await conn.execute("SELECT user_id FROM pfp_logs")
    rows = await cur.fetchall()
    assert rows[0]["user_id"] == 222

    today_start = datetime.combine(get_today_wib(), datetime.min.time(), tzinfo=TZ).timestamp()
    daily_rows = await db.get_pfp_daily_stats(conn, today_start - 100, now + 100)
    assert daily_rows[0]["user_id"] == 222
    assert daily_rows[0]["first_name"] == "OldUser"
    await conn.close()


# =============================================================================
# 6. CHECKER.PY IPC WORKER & RESILIENCE TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_qa_checker_forward_ipc_paths_and_malformed_requests():
    import checker

    conn, raw = _make_full_sqlite_conn(return_dict=True)
    now = time.time()

    # 1. Valid private channel batch forward
    await conn.execute(
        "INSERT INTO userbot_requests (chat_id, action, status, created_at, updated_at) VALUES ('0', 'FORWARD:-100555:10:12', 'PENDING', ?, ?)",
        (now, now),
    )
    # 2. Malformed action
    await conn.execute(
        "INSERT INTO userbot_requests (chat_id, action, status, created_at, updated_at) VALUES ('0', 'FORWARD:broken', 'PENDING', ?, ?)",
        (now, now),
    )
    # 3. Expired FORWARD (>120s)
    await conn.execute(
        "INSERT INTO userbot_requests (chat_id, action, status, created_at, updated_at) VALUES ('0', 'FORWARD:@ch:1:1', 'PENDING', ?, ?)",
        (now - 135, now - 135),
    )
    # 4. Expired RESOLVE (>30s)
    await conn.execute(
        "INSERT INTO userbot_requests (chat_id, action, status, created_at, updated_at) VALUES ('0', 'RESOLVE:@someone', 'PENDING', ?, ?)",
        (now - 45, now - 45),
    )
    await conn.commit()

    mock_checker_app = MagicMock()
    mock_checker_app.forward_messages = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])

    with patch.object(checker, "app", mock_checker_app), patch.object(checker, "KEEP_CH_ID", -100111):
        count = await checker.process_userbot_requests(conn)

    assert count == 4
    rows = await (await conn.execute("SELECT id, status, result FROM userbot_requests ORDER BY id ASC")).fetchall()
    assert rows[0]["status"] == "DONE"
    assert json.loads(rows[0]["result"])["forwarded"] == 3
    assert rows[1]["status"] == "ERROR"
    assert rows[2]["status"] == "ERROR" and rows[2]["result"] == "EXPIRED"
    assert rows[3]["status"] == "ERROR" and rows[3]["result"] == "EXPIRED"
    await conn.close()


# =============================================================================
# 7. CONCURRENCY, KLOTER WINDOW INTEGRITY & DISASTER RECOVERY
# =============================================================================


@pytest.mark.asyncio
async def test_qa_concurrency_two_manual_clicks_only_one_runs():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    db = AsyncMock()
    conn = MagicMock()
    db.get_setting.return_value = "0"
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}

    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_history(_):
        started.set()
        await proceed.wait()
        m = MagicMock()
        m.id = 1
        m.empty = False
        m.service = False
        m.from_user = None
        m.text = "Post"
        yield m

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock(return_value=1)
    mock_app.get_chat_history.side_effect = slow_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC"), \
         patch("bot.settings.OWNER_ID", 999), \
         patch("pyrogram.Client", return_value=mock_app):

        t1 = asyncio.create_task(execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=888))
        await started.wait()
        r2 = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=888)
        proceed.set()
        r1 = await t1

    assert r1 == (1, None)
    assert r2[0] == 0 and "sedang berjalan" in (r2[1] or "")


@pytest.mark.asyncio
async def test_qa_pfp_stats_and_kloter_cross_day_window_accuracy():
    """Verify kloter 1 (15:00) -> late evening /pfp -> next day 15:00 carries overnight logs accurately."""
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    bot = MagicMock()
    bot.send_message = AsyncMock()

    now_ref = datetime(2026, 11, 28, 15, 0, tzinfo=TZ).timestamp()
    day1_1400 = datetime(2026, 11, 27, 14, 0, tzinfo=TZ).timestamp()
    day1_1500 = datetime(2026, 11, 27, 15, 0, tzinfo=TZ).timestamp()
    day1_2130 = datetime(2026, 11, 27, 21, 30, tzinfo=TZ).timestamp()
    day2_1000 = datetime(2026, 11, 28, 10, 0, tzinfo=TZ).timestamp()

    await db.set_setting(conn, "keep_last_report_ts", str(day1_1500))
    # Before day1 15:00 -> already reported, MUST NOT recount
    await db.log_pfp_forward(conn, 10, 10, "@a", 1, 4, 4, day1_1400)
    # After day1 17:59 (overnight) -> MUST be included in day2 15:00
    await db.log_pfp_forward(conn, 10, 10, "@a", 5, 6, 2, day1_2130)
    # Day2 morning -> MUST be included in day2 15:00
    await db.log_pfp_forward(conn, 11, 11, "@b", 7, 9, 3, day2_1000)

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock(return_value=4)

    async def hist(_):
        for mid in (4, 3, 2, 1):
            m = MagicMock()
            m.id = mid
            m.empty = False
            m.service = False
            m.from_user = None
            m.text = f"P{mid}"
            yield m

    mock_app.get_chat_history.side_effect = hist

    with patch.dict(os.environ, {"USERBOT_SESSION": "test_session"}), \
         patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("bot.jobs.time.time", return_value=now_ref), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd, err = await execute_keep_to_post(bot, db, conn, is_manual=False, kloter_label="15:00 WIB")

    assert fwd == 4 and err is None
    owner_calls = [c[1]["text"] for c in bot.send_message.call_args_list if c[1]["chat_id"] == 999001]
    assert len(owner_calls) == 1
    assert "2x perintah (5 post masuk KEEP)" in owner_calls[0]
    assert "Terforward ke @DhruvaPoster:</b> 4 post" in owner_calls[0]
    assert "Selisih:</b> 1 post" in owner_calls[0]
    await conn.close()


@pytest.mark.asyncio
async def test_qa_aiosqlite_row_mock_compatibility_across_pfp_and_jobs():
    """Verify AiosqliteRowMock (Turso row adapter) works everywhere in PFP & jobs."""
    row = AiosqliteRowMock((101, "Alice", "alice_u", 5, 2), ["user_id", "first_name", "username", "total_posts", "total_commands"])
    d = dict(row)
    assert d["user_id"] == 101 and d.get("username") == "alice_u"

    stats_row = AiosqliteRowMock((3, 12), ["total_commands", "total_posts"])
    assert int(stats_row["total_commands"]) == 3
    assert int(stats_row["total_posts"]) == 12

    user_row = AiosqliteRowMock((6, "internal", '{"position_detail": ["d_pfp"]}'), ["telegram_id", "role", "profile_json"])
    mock_db = AsyncMock()
    mock_db.get_user.return_value = user_row
    with patch("bot.handlers.pfp.is_owner", return_value=False), patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        assert await pfp.is_authorized_pfp_admin(MagicMock(), mock_db, 6) is True


@pytest.mark.asyncio
async def test_qa_pyrogram_start_failure_recovers_lock_and_notifies_owner():
    """Verify lock is released when Pyrogram start() fails and subsequent run recovers."""
    ctx = MagicMock()
    ctx.application.bot_data = {"db": AsyncMock(), "conn": MagicMock()}
    ctx.application.bot_data["db"].get_setting.return_value = "0"
    ctx.application.bot_data["db"].get_pfp_kloter_stats.return_value = {"total_commands": 0, "total_posts": 0}
    ctx.bot.send_message = AsyncMock()
    ctx.job.name = "keep_to_post_1759"
    ctx.job.data = {"kloter_label": "17:59 WIB"}

    bad_app = MagicMock()
    bad_app.start = AsyncMock(side_effect=sqlite3.OperationalError("database is locked"))

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("pyrogram.Client", return_value=bad_app):
        await daily_keep_to_post(ctx)

    # Lock MUST NOT stay stuck after start() failure!
    assert get_keep_forward_lock().locked() is False
    # Owner MUST receive failure DM explaining session lock remediation
    ctx.bot.send_message.assert_called_once()
    assert "checker.session sedang dikunci" in ctx.bot.send_message.call_args[1]["text"]

    # Retry succeeds with healthy client
    good_app = MagicMock()
    good_app.start = AsyncMock()
    good_app.stop = AsyncMock()

    async def empty(_):
        if False:
            yield None

    good_app.get_chat_history.side_effect = empty
    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("pyrogram.Client", return_value=good_app):
        fwd, err = await execute_keep_to_post(ctx.bot, ctx.application.bot_data["db"], ctx.application.bot_data["conn"])
    assert fwd == 0 and err is None


@pytest.mark.asyncio
async def test_qa_daily_truncation_unicode_and_report_formatting_boundary():
    """Verify HTML escaping and >3300 char truncation with Unicode/special chars."""
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    today = get_today_wib()
    ts = datetime.combine(today, datetime.min.time(), tzinfo=TZ).timestamp() + 100

    for i in range(1, 140):
        uid = 5000 + i
        await conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) VALUES (?, ?, ?, 'student', '{}', 1.0, 1.0)",
            (uid, f"user_{i}", f"<Script&Name_{i}_🔥_VeryLongDisplayNameHere>"),
        )
        await db.log_pfp_forward(conn, uid, -1001, "@ch", 1, 1, 1, ts)
    await conn.commit()

    txt, kb = await pfp.get_pfp_daily_content(conn, db)
    assert len(txt) <= 4096
    assert "&lt;Script&amp;Name_1_" in txt
    assert "...dan" in txt

    # Negative diff in Owner report (extra direct post in KEEP outside /pfp)
    rep = _format_keep_kloter_owner_report("15:00 WIB <test>", 0, 0, 3, 3, is_manual=False)
    assert "&lt;test&gt;" in rep
    assert "+3 post (tambahan langsung di KEEP di luar /pfp)" in rep
    await conn.close()


def test_qa_sql_query_plans_use_indexes_no_full_table_scan():
    """Verify every periodic & interactive PFP/IPC/owner query uses an index."""
    raw = sqlite3.connect(":memory:")
    raw.executescript(SCHEMA)

    queries = {
        "pfp_daily": (
            "SELECT l.user_id, SUM(l.forwarded_count) FROM pfp_logs l "
            "LEFT JOIN users u ON l.user_id = u.telegram_id "
            "WHERE l.created_at >= ? AND l.created_at <= ? GROUP BY l.user_id",
            (1.0, 2.0),
        ),
        "pfp_weekly": (
            "SELECT l.user_id, l.forwarded_count, l.created_at FROM pfp_logs l "
            "WHERE l.created_at >= ? AND l.created_at <= ? ORDER BY l.created_at ASC",
            (1.0, 2.0),
        ),
        "pfp_kloter": (
            "SELECT COUNT(id), COALESCE(SUM(forwarded_count), 0) FROM pfp_logs "
            "WHERE created_at > ? AND created_at <= ?",
            (1.0, 2.0),
        ),
        "userbot_pending": (
            "SELECT * FROM userbot_requests WHERE status = 'PENDING'",
            (),
        ),
        "owner_lookup": (
            "SELECT telegram_id FROM users WHERE role = 'owner' LIMIT 1",
            (),
        ),
        "bot_settings_pk": (
            "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
            ("keep_last_fwd_id",),
        ),
    }

    for name, (sql, params) in queries.items():
        plan = " ".join(str(r) for r in raw.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall())
        assert "SCAN pfp_logs" not in plan, f"Full table scan in {name}: {plan}"
        assert "SCAN userbot_requests" not in plan, f"Full table scan in {name}: {plan}"
        assert "SCAN users" not in plan, f"Full table scan in {name}: {plan}"
        assert "USING INDEX" in plan or "USING COVERING INDEX" in plan, f"Expected index usage in {name}: {plan}"

    raw.close()


@pytest.mark.asyncio
async def test_qa_handler_registration_and_onboarding_fsm_isolation():
    """Verify PFP/post_keep handlers are registered in group 0 and do not clobber onboarding_step."""
    from telegram.ext import CallbackQueryHandler, CommandHandler
    from bot.handlers import setup_handlers

    app = Application.builder().token("123456:TESTTOKEN").build()
    setup_handlers(app, Database())
    grp0 = app.handlers.get(0, [])
    cmds = {c for h in grp0 if isinstance(h, CommandHandler) for c in h.commands}
    assert {"pfp", "post_keep", "pfp_post", "flush_keep"}.issubset(cmds)
    cb_patterns = [str(getattr(h.pattern, "pattern", "")) for h in grp0 if isinstance(h, CallbackQueryHandler)]
    assert "^pfp:" in cb_patterns

    # User mid-onboarding invokes /pfp -> onboarding_step stays intact
    conn, raw = _make_full_sqlite_conn()
    db = Database()
    await conn.execute(
        "INSERT INTO users (telegram_id, role, profile_json, onboarding_step, created_at, updated_at) VALUES (888, 'student', '{}', 'LENGKAPI:full_name', 1.0, 1.0)"
    )
    await conn.commit()

    up = MagicMock()
    up.effective_user.id = 888
    up.effective_chat.id = 888
    up.effective_message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []
    ctx.application.bot_data = {"db": db, "conn": conn}

    await pfp.cmd_pfp(up, ctx)
    row = await db.get_user(conn, 888)
    assert row["onboarding_step"] == "LENGKAPI:full_name"
    await conn.close()


@pytest.mark.asyncio
async def test_fix_keep_to_post_delegates_to_checker_ipc_without_session_lock():
    """
    When USERBOT_SESSION is empty (production VPS running checker.py + main.py),
    execute_keep_to_post delegates KEEP_TO_POST via userbot_requests IPC so main.py
    never opens checker.session alongside checker.py (preventing database is locked),
    and falls back to Bot API delete_messages for any undeleted_ids.
    """
    import checker

    conn, raw = _make_full_sqlite_conn(return_dict=True)
    db = Database()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_messages = AsyncMock()

    mock_checker_app = MagicMock()
    mock_checker_app.forward_messages = AsyncMock(return_value=[MagicMock(), MagicMock()])
    # Userbot delete fails/returns 0 -> main.py bot.delete_messages fallback must clean KEEP
    mock_checker_app.delete_messages = AsyncMock(return_value=0)

    async def hist(_):
        for mid in (202, 201):
            m = MagicMock()
            m.id = mid
            m.empty = False
            m.service = False
            m.from_user = None
            m.text = f"Keep {mid}"
            yield m

    mock_checker_app.get_chat_history.side_effect = hist

    async def run_checker_once():
        for _ in range(40):
            await asyncio.sleep(0.05)
            processed = await checker.process_userbot_requests(conn)
            if processed > 0:
                return processed
        return 0

    with patch.dict(os.environ, {"USERBOT_SESSION": ""}), \
         patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch.object(checker, "app", mock_checker_app), \
         patch.object(checker, "KEEP_CH_ID", -100111), \
         patch.object(checker, "POST_CH_ID", -100222), \
         patch("pyrogram.Client") as direct_client_cls:

        worker_task = asyncio.create_task(run_checker_once())
        fwd, err = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999001)
        processed = await worker_task

    assert processed == 1
    assert fwd == 2 and err is None
    # Crucial: main.py must NOT spawn a competing Pyrogram Client("checker")
    direct_client_cls.assert_not_called()
    # Bot API delete fallback cleaned [201, 202] when userbot delete_messages returned 0
    bot.delete_messages.assert_awaited_once_with(chat_id=-100111, message_ids=[201, 202])
    assert await db.get_setting(conn, "keep_last_fwd_id") == "202"
    await conn.close()


@pytest.mark.asyncio
async def test_fix_process_broadcast_queue_no_asyncio_unboundlocalerror():
    """Verify process_broadcast_queue runs without UnboundLocalError on 'asyncio'."""
    from bot.jobs import process_broadcast_queue

    ctx = MagicMock()
    db = AsyncMock()
    db.get_pending_broadcast_job.return_value = None
    ctx.application.bot_data = {"db": db, "conn": MagicMock()}

    await process_broadcast_queue(ctx)
    db.get_pending_broadcast_job.assert_awaited_once()
