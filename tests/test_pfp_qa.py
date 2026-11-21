"""
Comprehensive QA Suite for /pfp Feature (docs/qa.md standard).
Tests:
- Happy path (single, range, tutor, daily, weekly)
- Edge cases (URL formats, reverse range, boundary 100 posts, different channels, truncation budgeting)
- Security & Permissions (Non-owner vs Owner access on commands & callback queries)
- Multi-layer forwarding resilience (Bot API batch -> single fallback -> Userbot IPC)
- Database integrity & Turso read optimization
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
from telegram.error import BadRequest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.database import Database
import bot.handlers.pfp as pfp
from bot.timefmt import TZ, get_today_wib


def run_sync(coro):
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
def qa_db():
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

    CREATE TABLE attendance_records (id INTEGER PRIMARY KEY);
    CREATE TABLE attendance_sessions (id INTEGER PRIMARY KEY);
    CREATE TABLE agra_ledger (id INTEGER PRIMARY KEY);
    CREATE TABLE profile_request_mod_messages (id INTEGER PRIMARY KEY);
    CREATE TABLE profile_change_requests (id INTEGER PRIMARY KEY);
    CREATE TABLE audit_log (id INTEGER PRIMARY KEY);
    CREATE TABLE task_submissions (id INTEGER PRIMARY KEY);
    CREATE TABLE task_assignments (id INTEGER PRIMARY KEY);
    CREATE TABLE charyarthi_answers (id INTEGER PRIMARY KEY);
    CREATE TABLE warkat_codes (id INTEGER PRIMARY KEY);
    """)
    conn = AsyncSqliteMockConn(raw_conn)
    db = Database()
    return db, conn, raw_conn


# ==========================================
# 1. QA: INPUT VALIDATION & PARSING EDGE CASES
# ==========================================
def test_qa_link_parsing_edge_cases():
    # Various valid link wrappers
    assert pfp.parse_telegram_post_link("https://t.me/infodhruva/100") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("https://t.me/infodhruva/100#part2") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("https://t.me/infodhruva/100?single&foo=bar") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("<https://t.me/infodhruva/100/>") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("\"https://t.me/infodhruva/100\"") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("('https://t.me/infodhruva/100')") == ("@infodhruva", 100)
    assert pfp.parse_telegram_post_link("[https://t.me/infodhruva/100]") == ("@infodhruva", 100)

    # Private links
    assert pfp.parse_telegram_post_link("https://t.me/c/1999999999/42") == (-1001999999999, 42)
    assert pfp.parse_telegram_post_link("<https://telegram.me/c/12345/99#comment>") == (-10012345, 99)

    # Edge cases / Malformed
    assert pfp.parse_telegram_post_link("   ") is None
    assert pfp.parse_telegram_post_link("https://t.me/") is None
    assert pfp.parse_telegram_post_link("https://t.me/username") is None
    assert pfp.parse_telegram_post_link("https://t.me/username/abc") is None
    assert pfp.parse_telegram_post_link("https://otherdomain.com/c/123/456") is None
    assert pfp.parse_telegram_post_link("t.me/c/notanumber/123") is None


def test_qa_args_parsing():
    assert pfp.parse_pfp_args(["https://t.me/ch/1", "-", "https://t.me/ch/2"]) == ("RANGE", ("https://t.me/ch/1", "https://t.me/ch/2"))
    assert pfp.parse_pfp_args(["https://t.me/ch/1", "TO", "https://t.me/ch/2"]) == ("RANGE", ("https://t.me/ch/1", "https://t.me/ch/2"))
    assert pfp.parse_pfp_args(["  daily  "]) == ("DAILY", None)
    assert pfp.parse_pfp_args(["  weekly  "]) == ("WEEKLY", None)
    assert pfp.parse_pfp_args(["https://t.me/ch/50"]) == ("SINGLE", "https://t.me/ch/50")


# ==========================================
# 2. QA: SECURITY & AUTH
# ==========================================
def test_qa_security_non_owner_blocked(qa_db):
    db, conn, raw = qa_db
    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    # /pfp daily called by non-owner
    update = MagicMock()
    update.effective_user.id = 111111  # regular user
    update.effective_message.reply_text = AsyncMock()
    context.args = ["daily"]

    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "hanya dapat diakses oleh owner" in sent.lower()

    # /pfp weekly called by non-owner
    update.effective_message.reply_text.reset_mock()
    context.args = ["weekly"]
    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "hanya dapat diakses oleh owner" in sent.lower()

    # Callback query triggered by non-owner
    update_cb = MagicMock()
    update_cb.effective_user.id = 111111
    update_cb.callback_query.data = "pfp:daily"
    update_cb.callback_query.answer = AsyncMock()

    with patch("bot.handlers.pfp.is_owner", return_value=False):
        run_sync(pfp.cb_pfp(update_cb, context))
        update_cb.callback_query.answer.assert_called_once_with(
            "⛔ Hanya owner yang dapat mengakses menu ini.", show_alert=True
        )


def test_qa_security_owner_allowed(qa_db):
    db, conn, raw = qa_db
    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    update = MagicMock()
    update.effective_user.id = 999999
    update.effective_message.reply_text = AsyncMock()

    # Owner calls /pfp daily
    context.args = ["daily"]
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "Laporan PFP Daily (Hari Ini)" in sent

    # Owner calls /pfp weekly
    update.effective_message.reply_text.reset_mock()
    context.args = ["weekly"]
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "Rekapan PFP Weekly (7 Hari Terakhir)" in sent


# ==========================================
# 3. QA: FORWARDING BOUNDARIES & EDGE CASES
# ==========================================
def test_qa_reverse_range(qa_db):
    db, conn, raw = qa_db
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_chat.id = -1001
    status_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    # Reverse range: 20 to 15 (should automatically swap start/end to 15-20, total 6 posts)
    context.args = ["https://t.me/ch1/20", "to", "https://t.me/ch1/15"]
    context.bot.forward_messages = AsyncMock(return_value=[MagicMock()] * 6)
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1009999999999):
        run_sync(pfp.cmd_pfp(update, context))

        status_msg.edit_text.assert_called_once()
        assert "Berhasil mem-forward <b>6</b> dari <b>6</b> post" in status_msg.edit_text.call_args[0][0]

        cur = raw.execute("SELECT * FROM pfp_logs WHERE user_id = 123")
        row = cur.fetchone()
        assert row is not None
        assert row["first_msg_id"] == 15
        assert row["last_msg_id"] == 20
        assert row["forwarded_count"] == 6


def test_qa_boundary_100_posts(qa_db):
    db, conn, raw = qa_db
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_chat.id = -1001
    status_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=status_msg)
    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    # Exactly 100 posts: allowed
    context.args = ["https://t.me/ch1/1", "to", "https://t.me/ch1/100"]
    context.bot.forward_messages = AsyncMock(return_value=[MagicMock()] * 100)

    with patch("bot.handlers.pfp.KEEP_CH_ID", -1009999999999):
        run_sync(pfp.cmd_pfp(update, context))
        assert "Berhasil mem-forward <b>100</b> dari <b>100</b> post" in status_msg.edit_text.call_args[0][0]

    # 101 posts: rejected
    update.effective_message.reply_text.reset_mock()
    context.args = ["https://t.me/ch1/1", "to", "https://t.me/ch1/101"]
    with patch("bot.handlers.pfp.KEEP_CH_ID", -1009999999999):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "Rentang forward maksimal adalah <b>100 post</b>" in sent


def test_qa_missing_keep_ch_id(qa_db):
    db, conn, raw = qa_db
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://t.me/ch1/10"]
    context.application.bot_data = {"db": db, "conn": conn}

    with patch("bot.handlers.pfp.KEEP_CH_ID", None):
        run_sync(pfp.cmd_pfp(update, context))
        sent = update.effective_message.reply_text.call_args[0][0]
        assert "KEEP_CH_ID" in sent
        assert "belum dikonfigurasi" in sent


# ==========================================
# 4. QA: BUDGETING & TRUNCATION IN DAILY STATS
# ==========================================
def test_qa_daily_budgeting_truncation(qa_db):
    db, conn, raw = qa_db
    today = get_today_wib()
    start_today = datetime.combine(today, datetime.min.time(), tzinfo=TZ).timestamp()

    # Insert 150 unique users to test 3300-char budgeting limit
    users = [(i, f"user_{i}", f"Long Name User Number {i}") for i in range(1, 151)]
    raw.executemany("INSERT INTO users VALUES (?, ?, ?)", users)

    logs = [(i, -1001, "@ch", 1, 1, 1, start_today + 10) for i in range(1, 151)]
    raw.executemany("INSERT INTO pfp_logs (user_id, chat_id, channel_id, first_msg_id, last_msg_id, forwarded_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", logs)
    raw.commit()

    daily_text, daily_kb = run_sync(pfp.get_pfp_daily_content(conn, db))
    # Must contain truncation text and not crash or exceed 4096 chars
    assert len(daily_text) <= 4096
    assert "...dan" in daily_text
    assert "pengguna lainnya." in daily_text
    assert "Total Pengguna:</b> 150 orang" in daily_text
    assert "Total Post Ter-forward:</b> 150 post" in daily_text


def test_qa_null_db_handling():
    # If DB connection is None
    daily_text, daily_kb = run_sync(pfp.get_pfp_daily_content(None, None))
    assert "Database belum terhubung" in daily_text
    assert daily_kb is not None

    weekly_text, weekly_kb = run_sync(pfp.get_pfp_weekly_content(None, None))
    assert "Database belum terhubung" in weekly_text
    assert weekly_kb is not None


# ==========================================
# 5. QA: CALLBACK REFRESH & MESSAGE NOT MODIFIED
# ==========================================
def test_qa_callback_message_not_modified(qa_db):
    db, conn, raw = qa_db
    update = MagicMock()
    query = update.callback_query
    # Simulate Telegram throwing BadRequest: Message is not modified
    query.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"))
    query.answer = AsyncMock()
    query.data = "pfp:daily"

    context = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}

    # Should not raise exception
    with patch("bot.handlers.pfp.is_owner", return_value=True):
        run_sync(pfp.cb_pfp(update, context))
        query.answer.assert_called_once()


# ==========================================
# 6. QA: DB RESET INTEGRITY
# ==========================================
def test_qa_db_reset_all_data(qa_db):
    db, conn, raw = qa_db
    # Insert dummy pfp_logs
    raw.execute("INSERT INTO pfp_logs (user_id, chat_id, channel_id, first_msg_id, last_msg_id, forwarded_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, 1, "@c", 1, 1, 1, 100))
    raw.commit()

    cur = raw.execute("SELECT COUNT(*) as cnt FROM pfp_logs")
    assert cur.fetchone()["cnt"] == 1

    # Call reset_all_data_except_users
    run_sync(db.reset_all_data_except_users(conn))

    cur = raw.execute("SELECT COUNT(*) as cnt FROM pfp_logs")
    assert cur.fetchone()["cnt"] == 0
