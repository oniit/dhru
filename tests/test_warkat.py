from __future__ import annotations

import inspect
import time
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

from bot.database import (
    Database,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_CHARYARTHI,
    ROLE_INTERNAL,
    ROLE_PUBLIC,
)


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
def warkat_db():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    raw_conn.executescript("""
    CREATE TABLE users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        role TEXT NOT NULL DEFAULT 'public',
        onboarding_step TEXT,
        profile_json TEXT,
        created_at REAL,
        updated_at REAL
    );

    CREATE TABLE bot_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT
    );

    CREATE TABLE access_codes (
        code TEXT PRIMARY KEY,
        target_role TEXT,
        created_at REAL,
        created_by INTEGER,
        used_by INTEGER,
        used_at REAL
    );

    CREATE TABLE warkat_codes (
        code TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        created_by INTEGER NOT NULL,
        expires_charya REAL NOT NULL,
        created_gen INTEGER NOT NULL DEFAULT 1,
        max_generasi INTEGER NOT NULL,
        used_by INTEGER,
        used_at REAL,
        chosen_track TEXT,
        charya_div_1 TEXT,
        charya_div_2 TEXT,
        charya_div_3 TEXT
    );
    CREATE INDEX idx_warkat_used_by ON warkat_codes(used_by);
    CREATE INDEX idx_warkat_created_at ON warkat_codes(created_at);

    CREATE TABLE agra_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_telegram_id INTEGER NOT NULL,
        actor_telegram_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        description TEXT NOT NULL,
        chat_id INTEGER,
        message_id INTEGER,
        created_at REAL NOT NULL
    );

    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER,
        action TEXT NOT NULL,
        detail TEXT,
        created_at REAL NOT NULL
    );
    """)
    conn = AsyncSqliteMockConn(raw_conn)
    db = Database()
    return db, conn, raw_conn


def test_warkat_database_crud(warkat_db):
    db, conn, raw = warkat_db
    now = time.time()
    codes_data = [
        ("WARKAT-AAA-111", now, 999, now + 60 * 86400, 1, 3),
        ("WARKAT-BBB-222", now, 999, now + 60 * 86400, 1, 3),
    ]
    # 1. Create warkats
    run_sync(db.create_warkat_codes(conn, codes_data))

    # 2. Get available warkats
    avail = run_sync(db.get_available_warkat_codes(conn))
    assert len(avail) == 2
    assert avail[0]["code"] in ("WARKAT-AAA-111", "WARKAT-BBB-222")

    # 3. Get single warkat
    w = run_sync(db.get_warkat_code(conn, "warkat-aaa-111"))  # Case insensitive test
    assert w is not None
    assert w["code"] == "WARKAT-AAA-111"
    assert w["used_by"] is None

    # 4. Atomic redeem
    ok = run_sync(db.redeem_warkat_code(conn, "WARKAT-AAA-111", 12345, "pravesa"))
    assert ok is True

    # 5. Double redeem fails
    ok_second = run_sync(db.redeem_warkat_code(conn, "WARKAT-AAA-111", 67890, "pravesa"))
    assert ok_second is False

    # 6. Check state after redeem
    w_after = run_sync(db.get_warkat_code(conn, "WARKAT-AAA-111"))
    assert w_after["used_by"] == 12345
    assert w_after["chosen_track"] == "pravesa"

    avail_after = run_sync(db.get_available_warkat_codes(conn))
    assert len(avail_after) == 1
    assert avail_after[0]["code"] == "WARKAT-BBB-222"


def test_cmd_gencode_warkat_owner(warkat_db):
    from bot.handlers.commands import cmd_gencode_warkat

    db, conn, raw = warkat_db

    # Setup context and user
    user = MagicMock(id=999)
    message = MagicMock(text="/gencode_warkat 3")
    message.reply_text = AsyncMock()
    update = MagicMock(effective_user=user, message=message)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    # Test as owner
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(cmd_gencode_warkat(update, context))

    assert message.reply_text.called
    reply_text = message.reply_text.call_args[0][0]
    assert "Berhasil Membuat 3 Warkat Kehormatan" in reply_text
    assert "Masa Berlaku Charya:</b> 60 Hari" in reply_text
    assert "Masa Berlaku Pravesa:</b> 2 Generasi" in reply_text

    avail = run_sync(db.get_available_warkat_codes(conn))
    assert len(avail) == 3


def test_cmd_gencode_warkat_non_owner(warkat_db):
    from bot.handlers.commands import cmd_gencode_warkat

    db, conn, raw = warkat_db

    user = MagicMock(id=111)
    message = MagicMock(text="/gencode_warkat 1")
    message.reply_text = AsyncMock()
    update = MagicMock(effective_user=user, message=message)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    # Test as non-owner
    with patch("bot.handlers.commands.is_owner", return_value=False):
        run_sync(cmd_gencode_warkat(update, context))

    assert message.reply_text.called
    assert "Hanya owner yang berhak" in message.reply_text.call_args[0][0]
    avail = run_sync(db.get_available_warkat_codes(conn))
    assert len(avail) == 0


def test_handle_input_code_warkat_options(warkat_db):
    from bot.handlers.messages import handle_input_code

    db, conn, raw = warkat_db
    now = time.time()
    code = "WARKAT-TST-111"
    run_sync(db.create_warkat_codes(conn, [(code, now, 999, now + 60 * 86400, 1, 3)]))

    # Insert user in db
    raw.execute("INSERT INTO users (telegram_id, username, role) VALUES (?, ?, ?)", (555, "tester", "public"))
    raw.commit()

    user = MagicMock(id=555, username="tester", first_name="Tester", last_name="")
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = MagicMock(effective_user=user, message=message)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    run_sync(handle_input_code(update, context, code))

    assert message.reply_text.called
    text_sent = message.reply_text.call_args[0][0]
    assert "Warkat Kehormatan Terverifikasi!" in text_sent
    assert "Jalur Khusus Charya" in text_sent
    assert "Bebas Pravesa" in text_sent
    reply_markup = message.reply_text.call_args[1].get("reply_markup")
    assert reply_markup is not None
    # Check buttons
    buttons_data = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
    assert f"warkat:charya:{code}" in buttons_data
    assert f"warkat:pravesa:{code}" in buttons_data
    assert "warkat:cancel" in buttons_data


def test_handle_warkat_callback_pravesa(warkat_db):
    from bot.handlers.commands import handle_warkat_callback

    db, conn, raw = warkat_db
    now = time.time()
    code = "WARKAT-PRA-111"
    run_sync(db.create_warkat_codes(conn, [(code, now, 999, now + 60 * 86400, 1, 3)]))

    raw.execute("INSERT INTO users (telegram_id, username, role) VALUES (?, ?, ?)", (777, "alumni", "purna"))
    raw.commit()

    user = MagicMock(id=777, username="alumni", first_name="Alumni", last_name="")
    cb_query = MagicMock()
    cb_query.from_user = user
    cb_query.data = f"warkat:pravesa:{code}"
    cb_query.answer = AsyncMock()
    cb_query.edit_message_text = AsyncMock()

    update = MagicMock(callback_query=cb_query, effective_user=user)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}
    context.bot.send_message = AsyncMock()

    run_sync(handle_warkat_callback(update, context))

    assert cb_query.edit_message_text.called
    text = cb_query.edit_message_text.call_args[0][0]
    assert "Bebas Pravesa" in text
    assert "resmi menjadi <b>Shishya (Mahasiswa)</b>" in text

    # Verify role updated
    cur = raw.execute("SELECT role FROM users WHERE telegram_id = 777")
    assert cur.fetchone()["role"] == ROLE_STUDENT

    # Verify warkat redeemed
    w = run_sync(db.get_warkat_code(conn, code))
    assert w["used_by"] == 777
    assert w["chosen_track"] == "pravesa"


def test_handle_warkat_callback_charya_flow_and_submission(warkat_db):
    from bot.handlers.commands import handle_warkat_callback

    db, conn, raw = warkat_db
    now = time.time()
    code = "WARKAT-CHA-111"
    run_sync(db.create_warkat_codes(conn, [(code, now, 999, now + 60 * 86400, 1, 3)]))

    raw.execute("INSERT INTO users (telegram_id, username, first_name, role) VALUES (?, ?, ?, ?)", (888, "purnastaf", "Budi", "public"))
    raw.commit()

    user = MagicMock(id=888, username="purnastaf", first_name="Budi", last_name="")
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}
    context.user_data = {}
    context.bot.send_message = AsyncMock()

    # Step 1: User clicks Jalur Charya
    cb_query = MagicMock()
    cb_query.from_user = user
    cb_query.data = f"warkat:charya:{code}"
    cb_query.answer = AsyncMock()
    cb_query.edit_message_text = AsyncMock()
    update = MagicMock(callback_query=cb_query, effective_user=user)

    run_sync(handle_warkat_callback(update, context))
    assert "Pilihan Divisi 1" in cb_query.edit_message_text.call_args[0][0]

    # Step 2: Pick Divisi 1 (e.g. d_it)
    cb_query.data = f"warkat:cdiv1:{code}:d_it"
    run_sync(handle_warkat_callback(update, context))
    assert "Pilihan Divisi 2" in cb_query.edit_message_text.call_args[0][0]
    assert context.user_data["warkat_flow"]["d1"] == "d_it"

    # Step 3: Pick Divisi 2 (e.g. d_medkraf)
    cb_query.data = f"warkat:cdiv2:{code}:d_medkraf"
    run_sync(handle_warkat_callback(update, context))
    assert "Pilihan Divisi 3" in cb_query.edit_message_text.call_args[0][0]
    assert context.user_data["warkat_flow"]["d2"] == "d_medkraf"

    # Step 4: Pick Divisi 3 (e.g. d_humas)
    cb_query.data = f"warkat:cdiv3:{code}:d_humas"
    run_sync(handle_warkat_callback(update, context))
    conf_text = cb_query.edit_message_text.call_args[0][0]
    assert "Konfirmasi Pendaftaran Jalur Khusus Charya" in conf_text
    assert "@HRDhruvaBot" in conf_text
    assert context.user_data["warkat_flow"]["d3"] == "d_humas"

    # Step 5: Submit application
    cb_query.data = f"warkat:csubmit:{code}"
    with patch("bot.handlers.commands.PENDAFTAR_CH_ID", 1001), patch("bot.handlers.commands.SDM_CH_ID", 1002):
        run_sync(handle_warkat_callback(update, context))

    submit_text = cb_query.edit_message_text.call_args[0][0]
    assert "Pendaftaran Jalur Khusus Charya Berhasil Dikirim!" in submit_text

    # Check user role and profile in db
    cur = raw.execute("SELECT role, profile_json FROM users WHERE telegram_id = 888")
    u_row = cur.fetchone()
    assert u_row["role"] == ROLE_CHARYARTHI

    import json
    prof = json.loads(u_row["profile_json"])
    assert prof["target_division_1"] == "d_it"
    assert prof["target_division_2"] == "d_medkraf"
    assert prof["target_division_3"] == "d_humas"
    assert prof["application_status"] == "PENDING"

    # Verify warkat redeemed
    w = run_sync(db.get_warkat_code(conn, code))
    assert w["used_by"] == 888
    assert w["chosen_track"] == "charya"
    assert w["charya_div_1"] == "d_it"
    assert w["charya_div_2"] == "d_medkraf"
    assert w["charya_div_3"] == "d_humas"

    # Verify admin channel received notification with 3 accept buttons + 1 reject button
    assert context.bot.send_message.called
    pendaftar_call = [call for call in context.bot.send_message.call_args_list if call.kwargs.get("chat_id") == 1001][0]
    pendaftar_kb = pendaftar_call.kwargs.get("reply_markup")
    assert pendaftar_kb is not None
    admin_btn_cbs = [b.callback_data for r in pendaftar_kb.inline_keyboard for b in r]
    assert "charyarthi:acc:888:1" in admin_btn_cbs
    assert "charyarthi:acc:888:2" in admin_btn_cbs
    assert "charyarthi:acc:888:3" in admin_btn_cbs
    assert "charyarthi:rej:888" in admin_btn_cbs


def test_admin_acc_charyarthi_choice_3(warkat_db):
    from bot.handlers.commands import on_callback

    db, conn, raw = warkat_db
    import json
    prof_data = json.dumps({
        "full_name": "Budi",
        "target_division_1": "d_it",
        "target_division_2": "d_medkraf",
        "target_division_3": "d_humas",
        "application_status": "PENDING"
    })
    raw.execute("INSERT INTO users (telegram_id, username, first_name, role, profile_json) VALUES (?, ?, ?, ?, ?)",
                (888, "purnastaf", "Budi", ROLE_CHARYARTHI, prof_data))
    raw.commit()

    admin_user = MagicMock(id=999, first_name="Admin", username="admin")
    cb_query = MagicMock()
    cb_query.from_user = admin_user
    cb_query.data = "charyarthi:acc:888:3"
    cb_query.answer = AsyncMock()
    cb_query.edit_message_text = AsyncMock()
    cb_query.message.text_html = "Pendaftaran"

    update = MagicMock(callback_query=cb_query, effective_user=admin_user)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}
    context.bot.send_message = AsyncMock()

    with patch("bot.handlers.commands.is_admin_elevated", return_value=True):
        run_sync(on_callback(update, context))

    cur = raw.execute("SELECT role, profile_json FROM users WHERE telegram_id = 888")
    u_row = cur.fetchone()
    assert u_row["role"] == ROLE_INTERNAL
    prof = json.loads(u_row["profile_json"])
    assert prof["application_status"] == "ACCEPTED"
    assert prof["accepted_division"] == "d_humas"
    assert "d_humas" in prof["position_detail"]


def test_on_private_message_text_lc_full_name(warkat_db):
    """Memastikan on_private_message berhasil menangani input nama lengkap pada step TEXT_LC:full_name."""
    from bot.handlers.messages import on_private_message

    db, conn, raw = warkat_db
    raw.execute(
        "INSERT INTO users (telegram_id, username, first_name, role, onboarding_step) VALUES (?, ?, ?, ?, ?)",
        (333, "newuser", "Newbie", "public", "TEXT_LC:full_name"),
    )
    raw.commit()

    user = MagicMock(id=333, first_name="Newbie", username="newuser")
    message = MagicMock(text="Budi Santoso", photo=None, caption=None, chat_id=333)
    message.reply_text = AsyncMock()
    update = MagicMock(effective_user=user, message=message)
    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    run_sync(on_private_message(update, context))

    assert message.reply_text.called
    reply_msg = message.reply_text.call_args[0][0]
    assert "disimpan" in reply_msg or "lengkap" in reply_msg

    cur = raw.execute("SELECT profile_json, onboarding_step FROM users WHERE telegram_id = 333")
    row = cur.fetchone()
    assert row["onboarding_step"] is None
    import json
    prof = json.loads(row["profile_json"])
    assert prof["full_name"] == "Budi Santoso"
