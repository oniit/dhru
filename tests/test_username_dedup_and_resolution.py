from __future__ import annotations

import json
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.constants import MessageEntityType

import checker
from bot.database import AiosqliteRowMock, Database, ROLE_OWNER, ROLE_STUDENT, SCHEMA
from bot.handlers import commands
from bot.handlers.common import resolve_target_user


def _make_sqlite_conn():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(SCHEMA)

    class _Cur:
        def __init__(self, cur):
            self._cur = cur
            self.lastrowid = cur.lastrowid
            self.rowcount = cur.rowcount

        async def fetchone(self):
            return self._cur.fetchone()

        async def fetchall(self):
            return self._cur.fetchall()

    class _Conn:
        async def execute(self, sql, params=()):
            cur = raw.execute(sql, params)
            return _Cur(cur)

        async def executescript(self, script):
            raw.executescript(script)

        async def commit(self):
            raw.commit()

        async def close(self):
            raw.close()

    return _Conn(), raw


async def _insert_raw_user(conn, tid: int, username: str | None, first_name: str, updated_at: float, created_at: float = 100.0):
    await conn.execute(
        """
        INSERT INTO users (
            telegram_id, username, first_name, last_name, language_code,
            is_premium, is_bot, raw_profile_json, role, profile_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, '', 'id', 0, 0, '{}', 'student', '{}', ?, ?)
        """,
        (tid, username, first_name, created_at, updated_at),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_source_cleanup_on_upsert_and_sync():
    db = Database()
    conn, raw = _make_sqlite_conn()
    try:
        # 1. User A holds @siiqal via /start
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=101,
            username="Siiqal",
            first_name="Skylia Iqalla",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.touch_group_seen_user(
            conn,
            chat_id=-1001,
            telegram_id=101,
            username="Siiqal",
            first_name="Skylia Iqalla",
            last_name="",
            is_bot=False,
        )

        # 2. User B starts with @siiqal -> User A's username must be cleared in users & group_seen_users
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=202,
            username="siiqal",
            first_name="iqalla",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        u_a = await db.get_user(conn, 101)
        u_b = await db.get_user(conn, 202)
        assert u_a["username"] is None
        assert u_b["username"] == "siiqal"
        gs_a = raw.execute("SELECT username FROM group_seen_users WHERE telegram_id = 101").fetchone()
        assert gs_a["username"] is None

        # 3. Pre-existing duplicate in DB self-heals on sync_user_basic_info even if User C's own fields didn't change
        await _insert_raw_user(conn, 303, "dupe_un", "OldC", updated_at=100.0)
        await _insert_raw_user(conn, 404, "dupe_un", "NewC", updated_at=200.0)
        await db.sync_user_basic_info(conn, 404, "dupe_un", "NewC", "")
        u_303 = await db.get_user(conn, 303)
        u_404 = await db.get_user(conn, 404)
        assert u_303["username"] is None
        assert u_404["username"] == "dupe_un"

        # 4. User NOT in users table holding a username still clears stale users row
        await _insert_raw_user(conn, 505, "taken_un", "Stale", updated_at=100.0)
        await db.sync_user_basic_info(conn, 606, "taken_un", "Unregistered", "")
        u_505 = await db.get_user(conn, 505)
        assert u_505["username"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_touch_group_seen_user_clears_stale_username():
    db = Database()
    conn, raw = _make_sqlite_conn()
    try:
        await db.touch_group_seen_user(
            conn, chat_id=-1001, telegram_id=10, username="shared_un", first_name="Old", last_name="", is_bot=False
        )
        await db.touch_group_seen_user(
            conn, chat_id=-1002, telegram_id=20, username="Shared_Un", first_name="New", last_name="", is_bot=False
        )
        row_10 = raw.execute("SELECT username FROM group_seen_users WHERE telegram_id = 10").fetchone()
        row_20 = raw.execute("SELECT username FROM group_seen_users WHERE telegram_id = 20").fetchone()
        assert row_10["username"] is None
        assert row_20["username"] == "Shared_Un"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_find_ids_by_usernames_disambiguates_via_ipc_and_heals():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        # Insert 2 stale/duplicate rows where older updated_at (101) is actually the real Telegram owner
        await _insert_raw_user(conn, 101, "siiqal", "Skylia Iqalla", updated_at=100.0)
        await _insert_raw_user(conn, 202, "siiqal", "iqalla", updated_at=500.0)

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"siiqal": 101})) as mock_ipc:
            ids = await db.find_ids_by_usernames(conn, ["@siiqal", "siiqal"])
            mock_ipc.assert_awaited_once()
            assert ids == [101]

        # Stale row 202 must have been self-healed to NULL
        assert (await db.get_user(conn, 202))["username"] is None
        assert (await db.get_user(conn, 101))["username"] == "siiqal"

        # Subsequent call has only 1 row -> no IPC call
        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock()) as mock_ipc_2:
            ids2 = await db.find_ids_by_usernames(conn, ["siiqal"])
            mock_ipc_2.assert_not_called()
            assert ids2 == [101]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_find_ids_by_usernames_ipc_unregistered_and_timeout_fallbacks():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        # Case A: Both DB rows are stale; real Telegram owner (999) never /started
        await _insert_raw_user(conn, 101, "ghost", "Stale1", updated_at=100.0)
        await _insert_raw_user(conn, 202, "ghost", "Stale2", updated_at=200.0)

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"ghost": 999})):
            ids = await db.find_ids_by_usernames(conn, ["ghost"])
            assert ids == []
        assert (await db.get_user(conn, 101))["username"] is None
        assert (await db.get_user(conn, 202))["username"] is None

        # Case B: IPC fails/times out -> falls back to ONLY 1 ID (newest updated_at)
        await _insert_raw_user(conn, 303, "timeout_un", "Older", updated_at=100.0)
        await _insert_raw_user(conn, 404, "timeout_un", "Newer", updated_at=300.0)
        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={})):
            ids_fb = await db.find_ids_by_usernames(conn, ["timeout_un"])
            assert ids_fb == [404]

        # Case C: Empty / "@" only input
        assert await db.find_ids_by_usernames(conn, ["", "@"]) == []
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cmd_add_and_cmd_transfer_only_hit_single_recipient():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        await _insert_raw_user(conn, 1, "owner", "Owner", updated_at=100.0)
        await db.set_role(conn, 1, ROLE_OWNER)
        await _insert_raw_user(conn, 101, "siiqal", "Skylia Iqalla", updated_at=100.0)
        await _insert_raw_user(conn, 202, "siiqal", "iqalla", updated_at=200.0)
        await db.add_agra(conn, target_id=1, actor_id=1, amount=500, description="Modal", chat_id=None, message_id=None)

        # Build /add 3969 @siiqal penyesuaian
        msg = MagicMock(spec=Message)
        msg.text = "/add 3969 @siiqal penyesuaian"
        msg.chat_id = -1001
        msg.message_id = 55
        msg.reply_to_message = None
        msg.entities = [MessageEntity(type=MessageEntityType.MENTION, offset=10, length=7)]
        msg.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 1
        update.message = msg

        context = MagicMock()
        context.application.bot_data = {"conn": conn, "db": db}
        context.bot.send_message = AsyncMock()

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"siiqal": 202})):
            await commands.cmd_add(update, context)

        assert await db.agra_total(conn, 202) == 3969
        assert await db.agra_total(conn, 101) == 0
        reply = msg.reply_text.call_args[0][0]
        assert "iqalla" in reply
        assert "Skylia Iqalla" not in reply

        # Now test /transfer when duplicate exists -> deducts 100 once, credits only resolved user
        await _insert_raw_user(conn, 303, "dupe_tf", "OldTf", updated_at=100.0)
        await _insert_raw_user(conn, 404, "dupe_tf", "NewTf", updated_at=200.0)
        msg_tf = MagicMock(spec=Message)
        msg_tf.text = "/transfer 100 @dupe_tf hadiah"
        msg_tf.chat_id = -1001
        msg_tf.message_id = 56
        msg_tf.reply_to_message = None
        msg_tf.entities = [MessageEntity(type=MessageEntityType.MENTION, offset=14, length=8)]
        msg_tf.reply_text = AsyncMock()
        update.message = msg_tf

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"dupe_tf": 404})):
            await commands.cmd_transfer(update, context)

        assert await db.agra_total(conn, 1) == 400
        assert await db.agra_total(conn, 404) == 100
        assert await db.agra_total(conn, 303) == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_user_by_username_or_id_and_resolve_target_user_conflict():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        await _insert_raw_user(conn, 101, "siiqal", "Skylia", updated_at=100.0)
        await _insert_raw_user(conn, 202, "siiqal", "Iqalla", updated_at=500.0)

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"siiqal": 101})):
            u = await db.get_user_by_username_or_id(conn, "@siiqal")
            assert u is not None
            assert int(u["telegram_id"]) == 101

        # Group-seen conflict (insert manually to simulate pre-existing duplicate)
        await conn.execute(
            "INSERT INTO group_seen_users (chat_id, telegram_id, username, first_name, last_name, is_bot, last_seen_at) VALUES (-1, 701, 'grp_dupe', 'OldGrp', '', 0, 100.0)"
        )
        await conn.execute(
            "INSERT INTO group_seen_users (chat_id, telegram_id, username, first_name, last_name, is_bot, last_seen_at) VALUES (-2, 702, 'grp_dupe', 'NewGrp', '', 0, 300.0)"
        )
        await conn.commit()

        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"grp_dupe": 701})):
            tid, desc = await resolve_target_user(conn, db, "@grp_dupe")
            assert tid == 701
            assert "OldGrp" in desc

        # Empty "@" should safely return None without IPC
        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock()) as mock_ipc:
            tid_empty, _ = await resolve_target_user(conn, db, "@")
            assert tid_empty is None
            mock_ipc.assert_not_called()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_resolve_usernames_via_ipc_and_checker_batch_fallback():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        # Mock checker.app.get_users: batch fails, single calls succeed for valid user
        u_valid = MagicMock()
        u_valid.id = 77777
        u_valid.username = "ValidUser"
        u_valid.usernames = []

        async def fake_get_users(arg):
            if isinstance(arg, list):
                raise RuntimeError("UsernameNotOccupied in batch")
            if arg == "validuser":
                return u_valid
            raise RuntimeError("Not found")

        mock_app = MagicMock()
        mock_app.get_users = AsyncMock(side_effect=fake_get_users)

        req_id = await db.create_userbot_request(conn, "0", "RESOLVE:validuser,missinguser")
        with patch.object(checker, "app", mock_app):
            processed = await checker.process_userbot_requests(conn)
        assert processed == 1

        req_row = await db.get_userbot_request(conn, req_id)
        assert req_row["status"] == "DONE"
        assert json.loads(req_row["result"]) == {"validuser": 77777}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cmd_kick_group_seen_conflict_resolution():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        await _insert_raw_user(conn, 9000, "owner_kick", "Owner", updated_at=100.0)
        await db.set_role(conn, 9000, ROLE_OWNER)
        await conn.execute(
            "INSERT INTO group_seen_users (chat_id, telegram_id, username, first_name, last_name, is_bot, last_seen_at) VALUES (-10, 801, 'kick_dupe', 'OldKick', '', 0, 100.0)"
        )
        await conn.execute(
            "INSERT INTO group_seen_users (chat_id, telegram_id, username, first_name, last_name, is_bot, last_seen_at) VALUES (-10, 802, 'kick_dupe', 'NewKick', '', 0, 200.0)"
        )
        await conn.commit()

        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 9000
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.type = "group"
        update.effective_chat.id = -10
        update.message = MagicMock(spec=Message)
        update.message.text = "/kick @kick_dupe"
        update.message.caption = None
        update.message.reply_to_message = None
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.application.bot_data = {"conn": conn, "db": db}

        with (
            patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"kick_dupe": 801})),
            patch.object(commands, "is_admin_elevated", side_effect=lambda uid: uid == 9000),
            patch.object(commands, "_do_kick", new=AsyncMock()) as mock_do_kick,
        ):
            await commands.cmd_kick(update, context)
            mock_do_kick.assert_awaited_once()
            assert mock_do_kick.call_args[0][3] == 801
    finally:
        await conn.close()


def test_explain_query_plan_uses_indexes_no_full_table_scan():
    raw = sqlite3.connect(":memory:")
    raw.executescript(SCHEMA)
    try:
        queries = [
            (
                "find_ids_by_usernames",
                "SELECT telegram_id, lower(username) AS uname FROM users WHERE lower(username) IN ('siiqal') ORDER BY updated_at DESC, created_at DESC, telegram_id DESC",
            ),
            (
                "get_user_by_username_or_id",
                "SELECT * FROM users WHERE lower(username) = 'siiqal' ORDER BY updated_at DESC, created_at DESC, telegram_id DESC LIMIT 2",
            ),
            (
                "clear_stale_users",
                "UPDATE users SET username = NULL, updated_at = 1.0 WHERE lower(username) = 'siiqal' AND telegram_id != 1",
            ),
            (
                "clear_stale_group_seen",
                "UPDATE group_seen_users SET username = NULL WHERE lower(username) = 'siiqal' AND telegram_id != 1",
            ),
            (
                "group_seen_lookup",
                "SELECT telegram_id, MAX(last_seen_at) AS last_seen FROM group_seen_users WHERE lower(username) = 'siiqal' GROUP BY telegram_id ORDER BY last_seen DESC LIMIT 2",
            ),
        ]
        for name, sql in queries:
            plan_rows = raw.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
            plan = " | ".join(str(r[-1]) for r in plan_rows)
            assert "SCAN users" not in plan, f"Full table scan in {name}: {plan}"
            assert "SCAN group_seen_users" not in plan, f"Full table scan in {name}: {plan}"
    finally:
        raw.close()


@pytest.mark.asyncio
async def test_resolve_usernames_via_ipc_polling_and_third_user_and_profile_guard():
    db = Database()
    conn, _ = _make_sqlite_conn()
    try:
        # 1. Polling: PENDING -> DONE, ERROR, and timeout
        with (
            patch.object(db, "create_userbot_request", new=AsyncMock(return_value=42)),
            patch.object(
                db,
                "get_userbot_request",
                new=AsyncMock(
                    side_effect=[
                        {"status": "PENDING", "result": None},
                        {"status": "DONE", "result": json.dumps({"Siiqal": 12345})},
                    ]
                ),
            ),
        ):
            res = await db.resolve_usernames_via_ipc(conn, ["@Siiqal"], max_wait_seconds=1.0, poll_interval=0.01)
            assert res == {"siiqal": 12345}

        with (
            patch.object(db, "create_userbot_request", new=AsyncMock(return_value=43)),
            patch.object(db, "get_userbot_request", new=AsyncMock(return_value={"status": "ERROR", "result": "FAIL"})),
        ):
            res_err = await db.resolve_usernames_via_ipc(conn, ["siiqal"], max_wait_seconds=0.1, poll_interval=0.01)
            assert res_err == {}

        # 2. Third registered user (with old username) holds @siiqal on Telegram
        await _insert_raw_user(conn, 101, "siiqal", "Stale1", updated_at=100.0)
        await _insert_raw_user(conn, 202, "siiqal", "Stale2", updated_at=200.0)
        await _insert_raw_user(conn, 303, "old_303", "RealOwner", updated_at=50.0)
        with patch.object(db, "resolve_usernames_via_ipc", new=AsyncMock(return_value={"siiqal": 303})):
            ids = await db.find_ids_by_usernames(conn, ["siiqal"])
            assert ids == [303]
        assert (await db.get_user(conn, 101))["username"] is None
        assert (await db.get_user(conn, 202))["username"] is None
        assert (await db.get_user(conn, 303))["username"] == "siiqal"

        # 3. AiosqliteRowMock compatibility in resolve_target_user
        mock_row = AiosqliteRowMock([303, "siiqal", "RealOwner"], ["telegram_id", "username", "first_name"])
        with patch.object(db, "get_user_by_username_or_id", new=AsyncMock(return_value=mock_row)):
            tid, desc = await resolve_target_user(conn, db, "@siiqal")
            assert tid == 303
            assert "RealOwner" in desc

        # 4. cmd_profile guard when target ID does not exist in users
        await _insert_raw_user(conn, 1, "owner", "Owner", updated_at=100.0)
        await db.set_role(conn, 1, ROLE_OWNER)
        up_prof = MagicMock(spec=Update)
        up_prof.effective_user = MagicMock(spec=User)
        up_prof.effective_user.id = 1
        up_prof.message = MagicMock(spec=Message)
        up_prof.message.text = "/profile 999888777"
        up_prof.message.reply_text = AsyncMock()
        ctx_prof = MagicMock()
        ctx_prof.application.bot_data = {"conn": conn, "db": db}
        await commands.cmd_profile(up_prof, ctx_prof)
        up_prof.message.reply_text.assert_called_with("User tidak ditemukan.")
    finally:
        await conn.close()
