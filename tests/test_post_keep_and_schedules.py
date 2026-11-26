import asyncio
import sqlite3
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.database import Database
from bot.handlers.pfp import parse_pfp_args, is_authorized_pfp_admin, cmd_post_keep, cb_pfp, cmd_pfp
from bot.jobs import setup_jobs, execute_keep_to_post, get_keep_forward_lock, daily_keep_to_post


def _make_sqlite_async_conn():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row

    class _AsyncCur:
        def __init__(self, cur):
            self._cur = cur
            self.lastrowid = cur.lastrowid
            self.rowcount = cur.rowcount

        async def fetchone(self):
            return self._cur.fetchone()

        async def fetchall(self):
            return self._cur.fetchall()

    class _AsyncConn:
        async def execute(self, sql, params=()):
            cur = raw.execute(sql, params)
            return _AsyncCur(cur)

        async def executescript(self, script):
            raw.executescript(script)

        async def commit(self):
            raw.commit()

        async def close(self):
            raw.close()

    return _AsyncConn(), raw


def test_parse_pfp_args_post_subcommands():
    for sub in ["post", "POST", "flush", "FLUSH", "kirim", "forward", "manual"]:
        mode, data = parse_pfp_args([sub])
        assert mode == "POST"
        assert data is None


def test_setup_jobs_schedules_1500_and_1759():
    app = MagicMock()
    jq = MagicMock()
    app.job_queue = jq

    with patch("bot.settings.KEEP_CH_ID", -100123456789), \
         patch("bot.settings.POST_CH_ID", -100987654321), \
         patch("bot.jobs.PRESENCE_CH_ID", None):
        setup_jobs(app)

    run_daily_calls = jq.run_daily.call_args_list
    scheduled_times = []
    scheduled_names = []
    scheduled_labels = []
    for call in run_daily_calls:
        func = call[0][0]
        time_arg = call[0][1]
        name_arg = call[1].get("name")
        data_arg = call[1].get("data") or {}
        if func.__name__ == "daily_keep_to_post":
            scheduled_times.append((time_arg.hour, time_arg.minute))
            scheduled_names.append(name_arg)
            scheduled_labels.append(data_arg.get("kloter_label"))

    assert (15, 0) in scheduled_times
    assert (17, 59) in scheduled_times
    assert "keep_to_post_1500" in scheduled_names
    assert "keep_to_post_1759" in scheduled_names
    assert "15:00 WIB" in scheduled_labels
    assert "17:59 WIB" in scheduled_labels


@pytest.mark.asyncio
async def test_is_authorized_pfp_admin():
    db = AsyncMock()
    conn = MagicMock()

    # 1. Owner
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        assert await is_authorized_pfp_admin(conn, db, 111) is True

    # 2. Elevated Admin
    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=True):
        assert await is_authorized_pfp_admin(conn, db, 222) is True

    # 3. DB Admin role (simulate sqlite3.Row which has NO .get() method!)
    sqlite_conn = sqlite3.connect(":memory:")
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_conn.execute("CREATE TABLE t (role TEXT, profile_json TEXT)")
    sqlite_conn.execute("INSERT INTO t VALUES ('admin', '{}')")
    admin_row = sqlite_conn.execute("SELECT * FROM t").fetchone()

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        db.get_user.return_value = admin_row
        assert await is_authorized_pfp_admin(conn, db, 333) is True

    # 4. DB PFP division staff (position_detail contains d_pfp in profile_json)
    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        db.get_user.return_value = {
            "role": "internal",
            "profile_json": '{"position": "pfp", "position_detail": ["d_pfp"]}',
        }
        assert await is_authorized_pfp_admin(conn, db, 444) is True

    # 5. DB PFP division staff with only position_detail=["d_pfp"]
    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        db.get_user.return_value = {
            "role": "internal",
            "profile_json": '{"position_detail": ["d_pfp"]}',
        }
        assert await is_authorized_pfp_admin(conn, db, 445) is True

    # 6. Non-PFP internal staff (e.g. HRD / Dosen) -> False
    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        db.get_user.return_value = {
            "role": "internal",
            "profile_json": '{"position": "hrd", "position_detail": ["d_hrd"]}',
        }
        assert await is_authorized_pfp_admin(conn, db, 446) is False

    # 7. Regular student -> False
    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        db.get_user.return_value = {"role": "student", "profile_json": "{}"}
        assert await is_authorized_pfp_admin(conn, db, 555) is False

    sqlite_conn.close()


@pytest.mark.asyncio
async def test_cmd_post_keep_unauthorized():
    update = MagicMock()
    update.effective_user.id = 99999
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()

    with patch("bot.handlers.pfp.is_authorized_pfp_admin", AsyncMock(return_value=False)):
        await cmd_post_keep(update, context)

    update.effective_message.reply_text.assert_called_once()
    assert "tidak memiliki izin" in update.effective_message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_post_keep_success():
    update = MagicMock()
    update.effective_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=status_msg)
    context = MagicMock()

    with patch("bot.handlers.pfp.is_authorized_pfp_admin", AsyncMock(return_value=True)), \
         patch("bot.jobs.execute_keep_to_post", AsyncMock(return_value=(5, None))):
        await cmd_post_keep(update, context)

    status_msg.edit_text.assert_called_once()
    called_text = status_msg.edit_text.call_args[0][0]
    assert "Forward Manual Berhasil" in called_text
    assert "5" in called_text


@pytest.mark.asyncio
async def test_cmd_pfp_subcommand_post():
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["post"]

    with patch("bot.handlers.pfp.cmd_post_keep", AsyncMock()) as mock_cmd_post_keep:
        await cmd_pfp(update, context)
        mock_cmd_post_keep.assert_called_once_with(update, context)


@pytest.mark.asyncio
async def test_execute_keep_to_post_forwards_and_deletes():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_messages = AsyncMock()
    db = AsyncMock()
    conn = MagicMock()
    db.get_setting.return_value = "0"
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 2}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock()

    msg1 = MagicMock()
    msg1.id = 10
    msg1.empty = False
    msg1.service = False
    msg1.from_user.is_bot = False
    msg1.from_user.id = 777
    msg1.text = "Post 1"

    msg2 = MagicMock()
    msg2.id = 11
    msg2.empty = False
    msg2.service = False
    msg2.from_user.is_bot = False
    msg2.from_user.id = 777
    msg2.text = "Post 2"

    async def mock_history(_):
        for m in [msg2, msg1]:
            yield m

    mock_app.get_chat_history.side_effect = mock_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999888), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd_count, err = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999888)

    assert fwd_count == 2
    assert err is None

    mock_app.forward_messages.assert_called_once_with(
        chat_id=-100222,
        from_chat_id=-100111,
        message_ids=[10, 11]
    )
    mock_app.delete_messages.assert_called_once_with(
        chat_id=-100111,
        message_ids=[10, 11]
    )
    bot.delete_messages.assert_not_called()
    db.set_setting.assert_any_call(conn, "keep_last_fwd_id", "11")
    saved_keys = [c[0][1] for c in db.set_setting.call_args_list]
    assert "keep_last_report_ts" in saved_keys

    bot.send_message.assert_called_once()
    notif_text = bot.send_message.call_args[1]["text"]
    assert "Cek @DhruvaPoster" in notif_text
    assert "2 pesan" in notif_text
    assert "[Manual]" in notif_text


@pytest.mark.asyncio
async def test_execute_keep_to_post_delete_fallback_to_bot_api():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_messages = AsyncMock()
    db = AsyncMock()
    conn = MagicMock()
    db.get_setting.return_value = "0"
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock(side_effect=Exception("ChatAdminRequired"))

    msg1 = MagicMock()
    msg1.id = 25
    msg1.empty = False
    msg1.service = False
    msg1.from_user = None
    msg1.text = "Post fallback delete"

    async def mock_history(_):
        yield msg1

    mock_app.get_chat_history.side_effect = mock_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999888), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd_count, err = await execute_keep_to_post(bot, db, conn, is_manual=False, kloter_label="15:00 WIB")

    assert fwd_count == 1
    assert err is None
    mock_app.delete_messages.assert_called_once_with(chat_id=-100111, message_ids=[25])
    bot.delete_messages.assert_called_once_with(chat_id=-100111, message_ids=[25])


@pytest.mark.asyncio
async def test_database_get_pfp_kloter_stats():
    conn, raw = _make_sqlite_async_conn()
    db = Database()
    await conn.executescript(
        """
        CREATE TABLE pfp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            first_msg_id INTEGER NOT NULL,
            last_msg_id INTEGER NOT NULL,
            forwarded_count INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    # Before window (should be excluded: created_at == start_ts)
    await db.log_pfp_forward(conn, 1, 1, "@ch", 1, 1, 5, 1000.0)
    # Inside window
    await db.log_pfp_forward(conn, 1, 1, "@ch", 2, 4, 3, 1100.0)
    await db.log_pfp_forward(conn, 2, 1, "@ch", 5, 5, 1, 1200.0)
    # After window
    await db.log_pfp_forward(conn, 3, 1, "@ch", 6, 6, 2, 1300.0)

    stats = await db.get_pfp_kloter_stats(conn, 1000.0, 1250.0)
    assert stats == {"total_commands": 2, "total_posts": 4}
    await conn.close()


@pytest.mark.asyncio
async def test_daily_keep_to_post_notifies_owner_kloter_stats():
    conn, raw = _make_sqlite_async_conn()
    db = Database()
    await conn.executescript(
        """
        CREATE TABLE bot_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT);
        CREATE TABLE pfp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            first_msg_id INTEGER NOT NULL,
            last_msg_id INTEGER NOT NULL,
            forwarded_count INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    now_ts = time.time()
    await db.set_setting(conn, "keep_last_report_ts", str(now_ts - 3600))
    # 2x /pfp commands: 1 + 3 = 4 posts masuk KEEP
    await db.log_pfp_forward(conn, 101, 101, "@ch1", 1, 1, 1, now_ts - 1800)
    await db.log_pfp_forward(conn, 102, 102, "@ch2", 10, 12, 3, now_ts - 600)

    # Simulate 1 post was manually deleted by Owner in KEEP -> only 3 messages remain
    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock()

    msgs = []
    for mid in (303, 302, 301):
        m = MagicMock()
        m.id = mid
        m.empty = False
        m.service = False
        m.from_user = None
        m.text = f"Post {mid}"
        msgs.append(m)

    async def mock_history(_):
        for m in msgs:
            yield m

    mock_app.get_chat_history.side_effect = mock_history

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot.send_message = AsyncMock()
    context.bot.delete_messages = AsyncMock()
    context.job.name = "keep_to_post_1500"
    context.job.data = {"kloter_label": "15:00 WIB"}

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("pyrogram.Client", return_value=mock_app):

        await daily_keep_to_post(context)

    # Should send 1 message to KEEP_CH_ID and 1 private chat report to OWNER_ID
    assert context.bot.send_message.call_count == 2
    sent_by_chat = {c[1]["chat_id"]: c[1]["text"] for c in context.bot.send_message.call_args_list}
    assert -100111 in sent_by_chat
    assert 999001 in sent_by_chat

    owner_msg = sent_by_chat[999001]
    assert "15:00 WIB" in owner_msg
    assert "2x perintah (4 post masuk KEEP)" in owner_msg
    assert "Terforward ke @DhruvaPoster:</b> 3 post" in owner_msg
    assert "Selisih:</b> 1 post" in owner_msg

    await conn.close()


@pytest.mark.asyncio
async def test_daily_keep_to_post_all_deleted_manually_still_notifies_owner():
    conn, raw = _make_sqlite_async_conn()
    db = Database()
    await conn.executescript(
        """
        CREATE TABLE bot_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT);
        CREATE TABLE pfp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            first_msg_id INTEGER NOT NULL,
            last_msg_id INTEGER NOT NULL,
            forwarded_count INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    now_ts = time.time()
    await db.set_setting(conn, "keep_last_report_ts", str(now_ts - 1800))
    await db.log_pfp_forward(conn, 101, 101, "@ch1", 1, 2, 2, now_ts - 600)

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()

    async def empty_history(_):
        if False:
            yield None

    mock_app.get_chat_history.side_effect = empty_history

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot.send_message = AsyncMock()
    context.job.name = "keep_to_post_1759"
    context.job.data = {"kloter_label": "17:59 WIB"}

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("pyrogram.Client", return_value=mock_app):

        await daily_keep_to_post(context)

    # Only Owner DM should be sent (not KEEP channel message)
    context.bot.send_message.assert_called_once()
    call_kw = context.bot.send_message.call_args[1]
    assert call_kw["chat_id"] == 999001
    assert "17:59 WIB" in call_kw["text"]
    assert "1x perintah (2 post masuk KEEP)" in call_kw["text"]
    assert "Terforward ke @DhruvaPoster:</b> 0 post" in call_kw["text"]
    assert "Selisih:</b> 2 post" in call_kw["text"]

    await conn.close()


@pytest.mark.asyncio
async def test_daily_keep_to_post_empty_kloter_no_spam():
    conn, raw = _make_sqlite_async_conn()
    db = Database()
    await conn.executescript(
        """
        CREATE TABLE bot_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT);
        CREATE TABLE pfp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            first_msg_id INTEGER NOT NULL,
            last_msg_id INTEGER NOT NULL,
            forwarded_count INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    now_ts = time.time()
    await db.set_setting(conn, "keep_last_report_ts", str(now_ts - 1800))

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()

    async def empty_history(_):
        if False:
            yield None

    mock_app.get_chat_history.side_effect = empty_history

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot.send_message = AsyncMock()
    context.job.name = "keep_to_post_1500"
    context.job.data = {"kloter_label": "15:00 WIB"}

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999001), \
         patch("pyrogram.Client", return_value=mock_app):

        await daily_keep_to_post(context)

    context.bot.send_message.assert_not_called()
    await conn.close()


@pytest.mark.asyncio
async def test_execute_keep_to_post_concurrency_lock():
    bot = MagicMock()
    lock = get_keep_forward_lock()
    async with lock:
        with patch("bot.settings.KEEP_CH_ID", -100111), \
             patch("bot.settings.POST_CH_ID", -100222), \
             patch("bot.settings.API_ID", "12345"), \
             patch("bot.settings.API_HASH", "abcdef"):
            fwd_count, err = await execute_keep_to_post(bot, None, None, is_manual=True)
    assert fwd_count == 0
    assert err is not None
    assert "sedang berjalan" in err


@pytest.mark.asyncio
async def test_cb_pfp_post_button():
    update = MagicMock()
    query = update.callback_query
    query.data = "pfp:post"
    query.answer = AsyncMock()
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    query.message.reply_text = AsyncMock(return_value=status_msg)
    update.effective_user.id = 12345
    context = MagicMock()

    with patch("bot.handlers.pfp.is_authorized_pfp_admin", AsyncMock(return_value=True)), \
         patch("bot.jobs.execute_keep_to_post", AsyncMock(return_value=(3, None))):
        await cb_pfp(update, context)

    query.answer.assert_called_once()
    status_msg.edit_text.assert_called_once()
    assert "3" in status_msg.edit_text.call_args[0][0]
    assert "Forward Manual Berhasil" in status_msg.edit_text.call_args[0][0]


def test_is_keep_msg_excluded_includes_all_fail_notice():
    from bot.jobs import is_keep_msg_excluded

    msg = MagicMock()
    msg.empty = False
    msg.service = False
    msg.from_user = None
    msg.caption = None
    msg.text = "❌ Gagal! Seluruh pesan tidak dapat di-forward."
    assert is_keep_msg_excluded(msg, bot_id=123456) is True


@pytest.mark.asyncio
async def test_execute_keep_to_post_breaks_at_last_fwd_id():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    db = AsyncMock()
    conn = MagicMock()

    async def fake_get_setting(_, key, default=""):
        if key == "keep_last_fwd_id":
            return "100"
        return str(time.time() - 600)

    db.get_setting.side_effect = fake_get_setting
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    mock_app.delete_messages = AsyncMock(return_value=1)

    yielded_ids = []

    async def mock_history(_):
        for mid in (105, 100, 99, 98):
            m = MagicMock()
            m.id = mid
            m.empty = False
            m.service = False
            m.from_user = None
            m.text = f"Post {mid}"
            yielded_ids.append(mid)
            yield m

    mock_app.get_chat_history.side_effect = mock_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999888), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd_count, err = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999888)

    assert fwd_count == 1
    assert err is None
    assert yielded_ids == [105, 100]  # Berhenti tepat di msg 100 tanpa lanjut ke 99, 98
    mock_app.forward_messages.assert_called_once_with(
        chat_id=-100222,
        from_chat_id=-100111,
        message_ids=[105],
    )


@pytest.mark.asyncio
async def test_execute_keep_to_post_delete_fallback_when_pts_count_zero():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_messages = AsyncMock(return_value=True)
    db = AsyncMock()
    conn = MagicMock()
    db.get_setting.return_value = "0"
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.forward_messages = AsyncMock()
    # Simulasi Pyrogram delete_messages mengembalikan 0 tanpa exception
    mock_app.delete_messages = AsyncMock(return_value=0)

    msg = MagicMock()
    msg.id = 50
    msg.empty = False
    msg.service = False
    msg.from_user = None
    msg.text = "Post 50"

    async def mock_history(_):
        yield msg

    mock_app.get_chat_history.side_effect = mock_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999888), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd_count, err = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999888)

    assert fwd_count == 1
    assert err is None
    bot.delete_messages.assert_called_once_with(chat_id=-100111, message_ids=[50])


@pytest.mark.asyncio
async def test_execute_keep_to_post_retries_single_on_floodwait():
    from pyrogram.errors import FloodWait

    bot = MagicMock()
    bot.send_message = AsyncMock()
    db = AsyncMock()
    conn = MagicMock()
    db.get_setting.return_value = "0"
    db.get_pfp_kloter_stats.return_value = {"total_commands": 1, "total_posts": 1}

    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.delete_messages = AsyncMock(return_value=1)

    fw_exc = FloodWait(value=1)
    # 1st call: batch fail; 2nd call: FloodWait; 3rd call: success
    mock_app.forward_messages = AsyncMock(side_effect=[Exception("batch err"), fw_exc, [MagicMock()]])

    msg = MagicMock()
    msg.id = 77
    msg.empty = False
    msg.service = False
    msg.from_user = None
    msg.text = "Post FloodWait"

    async def mock_history(_):
        yield msg

    mock_app.get_chat_history.side_effect = mock_history

    with patch("bot.settings.KEEP_CH_ID", -100111), \
         patch("bot.settings.POST_CH_ID", -100222), \
         patch("bot.settings.API_ID", "12345"), \
         patch("bot.settings.API_HASH", "abcdef"), \
         patch("bot.settings.BOT_TOKEN", "123456:ABC-DEF"), \
         patch("bot.settings.OWNER_ID", 999888), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("pyrogram.Client", return_value=mock_app):

        fwd_count, err = await execute_keep_to_post(bot, db, conn, is_manual=True, triggered_by=999888)

    assert fwd_count == 1
    assert err is None


@pytest.mark.asyncio
async def test_daily_keep_to_post_notifies_owner_on_error():
    context = MagicMock()
    context.application.bot_data = {"db": MagicMock(), "conn": MagicMock()}
    context.bot.send_message = AsyncMock()
    context.job.name = "keep_to_post_1500"
    context.job.data = {"kloter_label": "15:00 WIB"}

    with patch("bot.jobs.execute_keep_to_post", AsyncMock(return_value=(0, "Sesi Pyrogram kedaluwarsa"))), \
         patch("bot.jobs._resolve_owner_chat_id", AsyncMock(return_value=999001)):
        await daily_keep_to_post(context)

    context.bot.send_message.assert_called_once()
    call_kw = context.bot.send_message.call_args[1]
    assert call_kw["chat_id"] == 999001
    assert "Kloter Keep → Poster Gagal" in call_kw["text"]
    assert "15:00 WIB" in call_kw["text"]
    assert "Sesi Pyrogram kedaluwarsa" in call_kw["text"]


@pytest.mark.asyncio
async def test_pfp_tutor_and_help_for_pfp_staff():
    from bot.handlers.commands import help_for_role
    from bot.database import ROLE_INTERNAL

    update = MagicMock()
    update.effective_user.id = 444555
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    db = AsyncMock()
    db.get_user.return_value = {
        "role": ROLE_INTERNAL,
        "profile_json": '{"position_detail": ["d_pfp"]}',
    }
    context.application.bot_data = {"db": db, "conn": MagicMock()}

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        await cmd_pfp(update, context)

    update.effective_message.reply_text.assert_called_once()
    kwargs = update.effective_message.reply_text.call_args[1]
    assert kwargs["reply_markup"] is not None
    btn_callbacks = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "pfp:post" in btn_callbacks

    help_text = help_for_role(ROLE_INTERNAL, {"position_detail": ["d_pfp"]})
    assert "/post_keep" in help_text
