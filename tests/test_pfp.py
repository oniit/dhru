"""
Unit & Integration Test Suite untuk fitur /pfp:
- Parsing link channel Telegram (publik & privat)
- Parsing argumen (/pfp, /pfp daily, /pfp weekly, /pfp link, /pfp link to link)
- Render tutorial & sub menu owner
- Rekap statistik harian (PFP Daily) & mingguan (PFP Weekly)
- Logika forward pesan (single, batch, fallback)
- Callback query navigation
"""

import asyncio
import inspect
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.database import Database
import bot.handlers.pfp as pfp
from bot.timefmt import TZ, get_today_wib


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


class AsyncSqliteMockConn:
    """Mock aiosqlite connection wrapping sqlite3 for unit tests."""
    def __init__(self, raw_conn):
        self._raw = raw_conn

    async def execute(self, sql, params=()):
        cur = self._raw.execute(sql, params)
        return AsyncSqliteMockCursor(cur)

    async def commit(self):
        self._raw.commit()


class AsyncSqliteMockCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    async def fetchone(self):
        r = self._cur.fetchone()
        return dict(r) if r is not None else None

    async def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid


@pytest.fixture
def test_db():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    raw_conn.executescript("""
    CREATE TABLE users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT
    );

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
    CREATE INDEX idx_pfp_logs_created_at ON pfp_logs(created_at);
    CREATE INDEX idx_pfp_logs_user_date ON pfp_logs(user_id, created_at);

    CREATE TABLE userbot_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        result TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    """)
    conn = AsyncSqliteMockConn(raw_conn)
    db = Database()
    return db, conn, raw_conn


# ==========================================
# 1. TEST PARSE TELEGRAM POST LINK
# ==========================================
def test_parse_telegram_post_link():
    # Public channel
    assert pfp.parse_telegram_post_link("https://t.me/infodhruva/123") == ("@infodhruva", 123)
    assert pfp.parse_telegram_post_link("t.me/infodhruva/123?single") == ("@infodhruva", 123)
    assert pfp.parse_telegram_post_link("<https://t.me/infodhruva/123>") == ("@infodhruva", 123)
    assert pfp.parse_telegram_post_link("<https://t.me/infodhruva/123") == ("@infodhruva", 123)
    assert pfp.parse_telegram_post_link("https://telegram.me/infodhruva/456/") == ("@infodhruva", 456)

    # Private channel
    assert pfp.parse_telegram_post_link("https://t.me/c/1234567890/789") == (-1001234567890, 789)
    assert pfp.parse_telegram_post_link("<https://telegram.me/c/987654321/1000>") == (-100987654321, 1000)

    # Invalid links
    assert pfp.parse_telegram_post_link("") is None
    assert pfp.parse_telegram_post_link("https://t.me/infodhruva") is None
    assert pfp.parse_telegram_post_link("https://t.me/joinchat/abcdef") is None
    assert pfp.parse_telegram_post_link("https://google.com/123") is None
    assert pfp.parse_telegram_post_link("t.me/c/invalid/123") is None


# ==========================================
# 2. TEST PARSE PFP ARGS
# ==========================================
def test_parse_pfp_args():
    assert pfp.parse_pfp_args([]) == ("TUTOR", None)
    assert pfp.parse_pfp_args([""]) == ("TUTOR", None)
    assert pfp.parse_pfp_args(["daily"]) == ("DAILY", None)
    assert pfp.parse_pfp_args(["DAILY"]) == ("DAILY", None)
    assert pfp.parse_pfp_args(["weekly"]) == ("WEEKLY", None)
    assert pfp.parse_pfp_args(["WEEKLY"]) == ("WEEKLY", None)

    # Single link
    assert pfp.parse_pfp_args(["https://t.me/ch/123"]) == ("SINGLE", "https://t.me/ch/123")

    # Range link with 'to'
    act, data = pfp.parse_pfp_args(["https://t.me/ch/100", "to", "https://t.me/ch/110"])
    assert act == "RANGE"
    assert data == ("https://t.me/ch/100", "https://t.me/ch/110")

    act, data = pfp.parse_pfp_args(["https://t.me/ch/100", "TO", "https://t.me/ch/110"])
    assert act == "RANGE"

    # Invalid range (more than 2 links with 'to')
    assert pfp.parse_pfp_args(["link1", "to", "link2", "to", "link3"])[0] == "INVALID"


# ==========================================
# 3. TEST TUTORIAL & OWNER MENU
# ==========================================
def test_get_pfp_tutorial_text():
    # Non-owner
    text_user, kb_user = pfp.get_pfp_tutorial_text(is_user_owner=False)
    assert "Panduan Penggunaan Perintah /pfp" in text_user
    assert "Sub Menu Khusus Owner" not in text_user
    assert kb_user is None

    # Owner
    text_owner, kb_owner = pfp.get_pfp_tutorial_text(is_user_owner=True)
    assert "Panduan Penggunaan Perintah /pfp" in text_owner
    assert "Sub Menu Khusus Owner" in text_owner
    assert kb_owner is not None
    button_texts = [btn.text for row in kb_owner.inline_keyboard for btn in row]
    assert "📊 PFP Daily" in button_texts
    assert "📅 PFP Weekly" in button_texts


# ==========================================
# 4. TEST DATABASE LOGS, DAILY & WEEKLY
# ==========================================
def test_pfp_database_stats(test_db):
    db, conn, raw = test_db

    # Insert dummy users
    raw.executemany("INSERT INTO users VALUES (?, ?, ?)", [
        (1001, "alicedev", "Alice"),
        (1002, "bobby", "Bob"),
    ])
    raw.commit()

    today = get_today_wib()
    start_today = datetime.combine(today, datetime.min.time(), tzinfo=TZ).timestamp()

    # Log several forwards
    run_sync(db.log_pfp_forward(conn, 1001, -100, "@ch1", 1, 5, 5, start_today + 100))
    run_sync(db.log_pfp_forward(conn, 1001, -100, "@ch1", 10, 10, 1, start_today + 200))
    run_sync(db.log_pfp_forward(conn, 1002, -100, "@ch2", 20, 24, 5, start_today + 300))
    # Unregistered user
    run_sync(db.log_pfp_forward(conn, 1003, -100, "@ch3", 1, 2, 2, start_today + 400))
    # Past days
    run_sync(db.log_pfp_forward(conn, 1001, -100, "@ch1", 50, 52, 3, start_today - 86400 * 2))

    # Test Daily Content
    daily_text, daily_kb = run_sync(pfp.get_pfp_daily_content(conn, db))
    assert "Laporan PFP Daily (Hari Ini)" in daily_text
    assert "<b>Alice</b> (@alicedev) — <b>6</b> post" in daily_text
    assert "<b>Bob</b> (@bobby) — <b>5</b> post" in daily_text
    assert "1003" in daily_text  # Unregistered user shows ID
    assert "Total Pengguna:</b> 3 orang" in daily_text
    assert "Total Post Ter-forward:</b> 13 post" in daily_text
    assert daily_kb is not None

    # Test Weekly Content
    weekly_text, weekly_kb = run_sync(pfp.get_pfp_weekly_content(conn, db))
    assert "Rekapan PFP Weekly (7 Hari Terakhir)" in weekly_text
    assert "Total Pengguna Unik:</b> 3 orang" in weekly_text
    assert "Total Seluruh Post:</b> 16 post" in weekly_text  # 13 today + 3 two days ago
    assert weekly_kb is not None


def test_pfp_daily_empty(test_db):
    db, conn, raw = test_db
    daily_text, _ = run_sync(pfp.get_pfp_daily_content(conn, db))
    assert "Belum ada pengguna yang mem-forward post hari ini." in daily_text


# ==========================================
# 5. TEST FORWARDING LOGIC
# ==========================================
def test_forward_posts_to_keep_single():
    bot = AsyncMock()
    bot.forward_message = AsyncMock(return_value=MagicMock())

    # Success single
    count, err = run_sync(pfp.forward_posts_to_keep(bot, None, None, -100999, "@ch1", 10, 10))
    assert count == 1
    assert err is None
    bot.forward_message.assert_called_once_with(chat_id=-100999, from_chat_id="@ch1", message_id=10)


def test_forward_posts_to_keep_batch_success():
    bot = AsyncMock()
    bot.forward_messages = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])

    count, err = run_sync(pfp.forward_posts_to_keep(bot, None, None, -100999, "@ch1", 1, 3))
    assert count == 3
    assert err is None
    bot.forward_messages.assert_called_once_with(chat_id=-100999, from_chat_id="@ch1", message_ids=[1, 2, 3])


def test_forward_posts_to_keep_batch_fallback_individual():
    bot = AsyncMock()
    # Batch raises exception (e.g. missing message 2)
    bot.forward_messages = AsyncMock(side_effect=Exception("Message 2 not found"))
    # Single succeeds for 1 and 3, fails for 2
    def fake_single(chat_id, from_chat_id, message_id):
        if message_id == 2:
            raise Exception("400 Message not found")
        return MagicMock()
    bot.forward_message = AsyncMock(side_effect=fake_single)

    count, err = run_sync(pfp.forward_posts_to_keep(bot, None, None, -100999, "@ch1", 1, 3))
    assert count == 2
    assert err is None


# ==========================================
# 6. TEST COMMAND HANDLER /PFP
# ==========================================
def test_cmd_pfp_tutor(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    update.effective_user.id = 555  # non-owner
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cmd_pfp(update, context))
        update.effective_message.reply_text.assert_called_once()
        sent_text = update.effective_message.reply_text.call_args[0][0]
        assert "Panduan Penggunaan Perintah /pfp" in sent_text
        assert "Sub Menu Khusus Owner" not in sent_text


def test_cmd_pfp_daily_access(test_db):
    db, conn, raw = test_db
    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    # Non-owner blocked
    update_user = MagicMock()
    update_user.effective_user.id = 555
    update_user.effective_message.reply_text = AsyncMock()
    context.args = ["daily"]

    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cmd_pfp(update_user, context))
        sent = update_user.effective_message.reply_text.call_args[0][0]
        assert "hanya dapat diakses oleh owner" in sent.lower()

    # Owner allowed
    update_owner = MagicMock()
    update_owner.effective_user.id = 999
    update_owner.effective_message.reply_text = AsyncMock()

    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cmd_pfp(update_owner, context))
        sent = update_owner.effective_message.reply_text.call_args[0][0]
        assert "Laporan PFP Daily (Hari Ini)" in sent


def test_cmd_pfp_single_forward_execution(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    update.effective_user.id = 777
    update.effective_chat.id = -100555
    status_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.args = ["https://t.me/test_ch/42"]
    context.bot.forward_message = AsyncMock(return_value=MagicMock())
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391):
        run_sync(pfp.cmd_pfp(update, context))

        # Check reply and log
        status_msg.edit_text.assert_called_once()
        assert "1 post</b> berhasil diforward" in status_msg.edit_text.call_args[0][0]

        # Verify database record
        cur = raw.execute("SELECT * FROM pfp_logs WHERE user_id = 777")
        row = cur.fetchone()
        assert row is not None
        assert row["channel_id"] == "@test_ch"
        assert row["first_msg_id"] == 42
        assert row["last_msg_id"] == 42
        assert row["forwarded_count"] == 1


def test_cmd_pfp_range_forward_execution(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    update.effective_user.id = 888
    update.effective_chat.id = -100666
    status_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.args = ["https://t.me/test_ch/10", "to", "https://t.me/test_ch/15"]
    context.bot.forward_messages = AsyncMock(return_value=[MagicMock()] * 6)
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391):
        run_sync(pfp.cmd_pfp(update, context))

        status_msg.edit_text.assert_called_once()
        assert "Berhasil mem-forward <b>6</b> dari <b>6</b> post" in status_msg.edit_text.call_args[0][0]

        cur = raw.execute("SELECT * FROM pfp_logs WHERE user_id = 888")
        row = cur.fetchone()
        assert row is not None
        assert row["first_msg_id"] == 10
        assert row["last_msg_id"] == 15
        assert row["forwarded_count"] == 6


def test_cmd_pfp_range_different_channels(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://t.me/channel1/10", "to", "https://t.me/channel2/15"]
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "Kedua tautan harus berasal dari channel yang sama" in sent


def test_cmd_pfp_range_exceeds_max(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://t.me/channel1/1", "to", "https://t.me/channel1/105"]
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "Rentang forward maksimal adalah <b>100 post</b>" in sent


# ==========================================
# 7. TEST CALLBACK QUERY HANDLER
# ==========================================
def test_cb_pfp(test_db):
    db, conn, raw = test_db
    update = MagicMock()
    query = update.callback_query
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()
    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    # Non-owner blocked with alert
    update.effective_user.id = 123
    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cb_pfp(update, context))
        query.answer.assert_called_once_with("⛔ Hanya owner yang dapat mengakses menu ini.", show_alert=True)

    # Owner switches to daily
    query.reset_mock()
    query.data = "pfp:daily"
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cb_pfp(update, context))
        query.edit_message_text.assert_called_once()
        assert "Laporan PFP Daily (Hari Ini)" in query.edit_message_text.call_args[0][0]

    # Owner switches to weekly
    query.reset_mock()
    query.data = "pfp:weekly"
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cb_pfp(update, context))
        query.edit_message_text.assert_called_once()
        assert "Rekapan PFP Weekly (7 Hari Terakhir)" in query.edit_message_text.call_args[0][0]

    # Owner switches back to menu
    query.reset_mock()
    query.data = "pfp:menu"
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cb_pfp(update, context))
        query.edit_message_text.assert_called_once()
        assert "Panduan Penggunaan Perintah /pfp" in query.edit_message_text.call_args[0][0]


# ==========================================
# 8. TEST USERBOT IPC FALLBACK
# ==========================================
def test_forward_via_userbot_ipc_success(test_db):
    db, conn, raw = test_db

    with patch.object(db, "create_userbot_request", new_callable=AsyncMock) as mock_create, \
         patch.object(db, "get_userbot_request", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_create.return_value = 123
        mock_get.return_value = {"status": "DONE", "result": json.dumps({"forwarded": 4})}

        count = run_sync(pfp._forward_via_userbot_ipc(conn, db, "@src_ch", 1, 4))
        assert count == 4
        mock_create.assert_called_once_with(conn, "0", "FORWARD:@src_ch:1:4")
        mock_get.assert_called_once_with(conn, 123)


def test_forward_posts_to_keep_ipc_fallback(test_db):
    db, conn, raw = test_db
    bot = AsyncMock()
    # Bot throws ChatNotFound (bot not in private channel)
    bot.forward_message = AsyncMock(side_effect=Exception("Chat not found"))

    with patch("bot.handlers.pfp._forward_via_userbot_ipc", return_value=1) as mock_ipc:
        count, err = run_sync(pfp.forward_posts_to_keep(bot, conn, db, -1004387877391, -1001234567890, 50, 50))
        assert count == 1
        assert err is None
        mock_ipc.assert_called_once_with(conn, db, -1001234567890, 50, 50)

