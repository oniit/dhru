"""
Test Suite: Mass Setrole Purna & Tutup Generasi
Memverifikasi fungsionalitas transisi peran massal ke Purna Shishya (Alumni) saat tutup generasi:
1. Parsing varian perintah (/setrole purna all|massal|shishya|student|semua|bem).
2. Proteksi keamanan (hanya role purna yang diizinkan massal, owner-only).
3. Eksekusi Database.mass_set_role_purna (pembekuan SKS, preservasi NIM, pembersihan kelas/UKM).
4. Filter target shishya vs bem vs all.
5. Handlers /setrole dan /tutup_generasi.
6. Preservasi identitas akademik untuk /transkrip dan /ijazah self-service.
"""

import asyncio
import inspect
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.database import (
    Database,
    SCHEMA,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_INTERNAL,
    ROLE_BEM,
    ROLE_STUDENT,
    ROLE_PURNA,
    ROLE_MABA,
    ROLE_PUBLIC,
)
from bot.settings import OWNER_ID, CHOICES
from bot.setrole_parse import parse_setrole_command, ParsedSetrole
from bot.handlers import commands, graduation, common
from telegram import Update, Message, User, Chat, MessageEntity
from telegram.constants import MessageEntityType


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


class RowMock:
    def __init__(self, row):
        self._row = row

    def keys(self):
        return self._row.keys()

    def __getitem__(self, key):
        return self._row[key]

    def get(self, key, default=None):
        try:
            val = self._row[key]
            return val if val is not None else default
        except (KeyError, IndexError):
            return default

    def __iter__(self):
        return iter(self._row.keys())


class AsyncCursorAdapter:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = cur.lastrowid
        self.rowcount = cur.rowcount

    async def fetchone(self):
        r = self._cur.fetchone()
        return RowMock(r) if r is not None else None

    async def fetchall(self):
        return [RowMock(r) for r in self._cur.fetchall()]


class AsyncSqliteAdapter:
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return AsyncCursorAdapter(cur)

    async def executemany(self, sql, params_seq):
        self._conn.executemany(sql, params_seq)

    async def executescript(self, sql_script):
        self._conn.executescript(sql_script)

    async def commit(self):
        self._conn.commit()

    async def close(self):
        pass


def make_mock_user(uid: int, username: str = "tester", first_name: str = "Test", role: str = ROLE_PUBLIC):
    u = MagicMock(spec=User)
    u.id = uid
    u.username = username
    u.first_name = first_name
    u.last_name = ""
    u.language_code = "id"
    u.is_premium = False
    u.is_bot = False
    u.to_dict = MagicMock(return_value={"id": uid, "username": username, "first_name": first_name})
    return u


def make_mock_update(user: User, text: str = "", chat_type: str = "private", reply_to: Message = None):
    up = MagicMock(spec=Update)
    up.effective_user = user
    chat = MagicMock(spec=Chat)
    chat.id = user.id if chat_type == "private" else -100888888
    chat.type = chat_type
    chat.title = "Dhruva Group" if chat_type != "private" else None
    up.effective_chat = chat

    msg = MagicMock(spec=Message)
    msg.text = text
    msg.message_id = 1000 + (hash(text) % 1000)
    msg.chat_id = chat.id
    msg.chat = chat
    msg.from_user = user
    msg.reply_to_message = reply_to
    msg.reply_text = AsyncMock()
    msg.reply_html = AsyncMock()
    entities = []
    for m in re.finditer(r"@(\w+)", text):
        e = MagicMock(spec=MessageEntity)
        e.type = MessageEntityType.MENTION
        e.offset = m.start()
        e.length = m.end() - m.start()
        entities.append(e)
    msg.entities = tuple(entities)
    up.message = msg
    up.callback_query = None
    return up


def setup_test_db():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    clean_schema = re.sub(r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_users_student_id[^;]+;", "", SCHEMA, flags=re.IGNORECASE)
    raw.executescript(clean_schema)

    # Runtime column migrations
    migrations = [
        "ALTER TABLE attendance_sessions ADD COLUMN announce_message_id INTEGER",
        "ALTER TABLE profile_change_requests ADD COLUMN moderator_prompt_text TEXT",
        "ALTER TABLE attendance_records ADD COLUMN status TEXT NOT NULL DEFAULT 'hadir'",
        "ALTER TABLE access_codes ADD COLUMN target_role TEXT NOT NULL DEFAULT 'student'",
        "ALTER TABLE promo_verifications ADD COLUMN promo_type TEXT NOT NULL DEFAULT 'lpm'",
        "ALTER TABLE bot_chats ADD COLUMN greeting_message TEXT",
    ]
    for sql in migrations:
        try:
            raw.execute(sql)
        except Exception:
            pass

    conn = AsyncSqliteAdapter(raw)
    db = Database(path=":memory:")
    return db, conn


def test_parsing():
    print("--- 1. Testing Parser /setrole ---")
    u = make_mock_user(OWNER_ID, "founder", "Owner")

    # Mass all
    up = make_mock_update(u, "/setrole purna all")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.role == "purna"
    assert p.is_mass is True
    assert p.mass_target == "all"
    print("  [PASS] /setrole purna all parsed as mass: all")

    # Mass shishya
    up = make_mock_update(u, "/setrole purna shishya")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.is_mass is True
    assert p.mass_target == "shishya"
    print("  [PASS] /setrole purna shishya parsed as mass: shishya")

    # Mass student
    up = make_mock_update(u, "/setrole purna student")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.is_mass is True
    assert p.mass_target == "student"
    print("  [PASS] /setrole purna student parsed as mass: student")

    # Mass bem
    up = make_mock_update(u, "/setrole purna bem")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.is_mass is True
    assert p.mass_target == "bem"
    print("  [PASS] /setrole purna bem parsed as mass: bem")

    # Mass semua
    up = make_mock_update(u, "/setrole purna semua")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.is_mass is True
    assert p.mass_target == "semua"
    print("  [PASS] /setrole purna semua parsed as mass: semua")

    # Normal mention (NOT mass)
    up = make_mock_update(u, "/setrole purna @aluna")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.is_mass is False
    assert "aluna" in p.mention_usernames
    print("  [PASS] /setrole purna @aluna parsed as specific mention")

    # No args -> None
    up = make_mock_update(u, "/setrole")
    assert parse_setrole_command(up.message) is None
    print("  [PASS] /setrole without args returns None")

    # Mass syntax on other roles
    up = make_mock_update(u, "/setrole admin all")
    p = parse_setrole_command(up.message)
    assert p is not None
    assert p.role == "admin"
    assert p.is_mass is True
    print("  [PASS] /setrole admin all parsed for downstream security gate")


def test_security_guards():
    print("\n--- 2. Testing Security Guards ---")
    db, conn = setup_test_db()
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")
    student_user = make_mock_user(2001, "mhs1", "Mahasiswa")

    ctx = MagicMock()
    ctx.application.bot_data = {"conn": conn, "db": db}
    ctx.bot = AsyncMock()

    # 1. Non-owner blocked from /setrole
    up_unauth = make_mock_update(student_user, "/setrole purna all")
    run_sync(commands.cmd_setrole(up_unauth, ctx))
    call_args = up_unauth.message.reply_text.call_args[0][0]
    assert "Hanya owner" in call_args
    print("  [PASS] Non-owner blocked from /setrole purna all")

    # 2. Non-owner blocked from /generasi_tutup
    up_tg_unauth = make_mock_update(student_user, "/generasi_tutup")
    run_sync(commands.cmd_generasi_tutup(up_tg_unauth, ctx))
    call_args = up_tg_unauth.message.reply_text.call_args[0][0]
    assert "Hanya owner" in call_args
    print("  [PASS] Non-owner blocked from /generasi_tutup")

    # 3. Owner attempts /setrole admin all -> MUST BE REJECTED
    up_exploit = make_mock_update(owner_user, "/setrole admin all")
    run_sync(commands.cmd_setrole(up_exploit, ctx))
    call_args = up_exploit.message.reply_text.call_args[0][0]
    assert "Fitur massal" in call_args
    assert "hanya diizinkan untuk mengubah peran ke" in call_args
    print("  [PASS] Exploitative mass role change (/setrole admin all) strictly rejected")


def test_database_mass_set_role_purna():
    print("\n--- 3. Testing Database.mass_set_role_purna & Identity Retention ---")
    db, conn = setup_test_db()
    now = time.time()

    # Seed users: 2 students, 1 bem, 1 internal (dosen)
    users_data = [
        (
            101,
            "shishya_aluna",
            "Aluna",
            ROLE_STUDENT,
            {
                "full_name": "Aluna Sagita",
                "faculty": "f_filsafat",
                "major": "jur_filsafat",
                "student_id": "2004010093",
                "class_enrolled": ["ti_dasar", "ti_lanjut"],
                "club_enrolled": ["ukm_tari"],
                "total_sks": 24,
                "accumulated_sks": 0,
            },
        ),
        (
            102,
            "shishya_bima",
            "Bima",
            ROLE_STUDENT,
            {
                "full_name": "Bima Arya",
                "faculty": "f_hukum",
                "major": "jur_hukum",
                "student_id": "2004020050",
                "class_enrolled": ["ti_dasar"],
                "total_sks": 18,
                "accumulated_sks": 0,
            },
        ),
        (
            103,
            "bem_citra",
            "Citra",
            ROLE_BEM,
            {
                "full_name": "Citra Lestari",
                "faculty": "f_filsafat",
                "major": "jur_filsafat",
                "student_id": "2004010010",
                "bem_position": "ketua_bem",
                "class_enrolled": ["ti_dasar"],
                "total_sks": 20,
                "accumulated_sks": 0,
            },
        ),
        (
            104,
            "dosen_dharma",
            "Dharma",
            ROLE_INTERNAL,
            {
                "full_name": "Dr. Dharma",
                "position_detail": ["d_dosen"],
                "teaching_classes": ["ti_dasar"],
            },
        ),
    ]

    for uid, uname, fname, role, prof in users_data:
        run_sync(
            conn.execute(
                "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, uname, fname, role, json.dumps(prof), now, now),
            )
        )
    run_sync(conn.commit())

    # Execute mass transition for "all"
    total, counts, processed = run_sync(db.mass_set_role_purna(conn, OWNER_ID, "all"))

    assert total == 3
    assert counts.get(ROLE_STUDENT) == 2
    assert counts.get(ROLE_BEM) == 1
    print(f"  [PASS] mass_set_role_purna processed {total} users (Shishya: {counts[ROLE_STUDENT]}, BEM: {counts[ROLE_BEM]})")

    # Check User 101 (Aluna)
    r101 = run_sync(conn.execute("SELECT role, profile_json FROM users WHERE telegram_id = 101"))
    row101 = run_sync(r101.fetchone())
    assert row101["role"] == ROLE_PURNA
    p101 = json.loads(row101["profile_json"])
    assert p101.get("accumulated_sks") == 24
    assert p101.get("total_sks") == 24
    assert p101.get("student_id") == "2004010093", "NIM must be permanently retained for Purna alumni!"
    assert "class_enrolled" not in p101, "Active classes must be pruned!"
    assert "club_enrolled" not in p101, "Active clubs must be pruned!"
    print("  [PASS] User 101: Role=purna, SKS banked=24, NIM=2004010093 retained, classes/clubs pruned")

    # Check User 103 (BEM Citra)
    r103 = run_sync(conn.execute("SELECT role, profile_json FROM users WHERE telegram_id = 103"))
    row103 = run_sync(r103.fetchone())
    assert row103["role"] == ROLE_PURNA
    p103 = json.loads(row103["profile_json"])
    assert p103.get("accumulated_sks") == 20
    assert p103.get("student_id") == "2004010010"
    print("  [PASS] User 103 (BEM): Role=purna, SKS banked=20, NIM=2004010010 retained")

    # Check User 104 (Dosen Dharma)
    r104 = run_sync(conn.execute("SELECT role FROM users WHERE telegram_id = 104"))
    row104 = run_sync(r104.fetchone())
    assert row104["role"] == ROLE_INTERNAL, "Staff/Internal must not be affected by student graduation!"
    print("  [PASS] User 104 (Dosen): Remained role internal")

    # Check Audit Log
    cur_aud = run_sync(conn.execute("SELECT action, detail FROM audit_log WHERE action = 'mass_set_role_purna'"))
    aud_rows = run_sync(cur_aud.fetchall())
    assert len(aud_rows) == 3
    print("  [PASS] Audit log recorded 3 mass_set_role_purna events")


def test_command_setrole_purna_all_flow():
    print("\n--- 4. Testing End-to-End cmd_setrole purna all ---")
    db, conn = setup_test_db()
    now = time.time()
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")

    # Seed 1 student
    prof = {
        "full_name": "Aluna Sagita",
        "faculty": "f_filsafat",
        "major": "jur_filsafat",
        "student_id": "2004010093",
        "class_enrolled": ["ti_dasar"],
        "total_sks": 24,
    }
    run_sync(
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (301, "aluna", "Aluna", ROLE_STUDENT, json.dumps(prof), now, now),
        )
    )
    run_sync(conn.commit())

    ctx = MagicMock()
    ctx.application.bot_data = {"conn": conn, "db": db}
    ctx.bot.send_message = AsyncMock()

    up = make_mock_update(owner_user, "/setrole purna all")
    run_sync(commands.cmd_setrole(up, ctx))

    # Verification of reply text
    assert up.message.reply_text.called
    reply_msg = up.message.reply_text.call_args[0][0]
    assert "Transisi Massal ke Purna Shishya Selesai" in reply_msg
    assert "Total mahasiswa yang diluluskan: <b>1</b> orang" in reply_msg
    assert "Aluna Sagita" in reply_msg
    assert "2004010093" in reply_msg
    print("  [PASS] cmd_setrole purna all executed successfully and returned formatted summary")

    # Verification of notification sent to student 301
    assert ctx.bot.send_message.called
    notif_target = ctx.bot.send_message.call_args[1].get("chat_id")
    notif_text = ctx.bot.send_message.call_args[1].get("text")
    assert notif_target == 301
    assert "Pemberitahuan Kelulusan Generasi" in notif_text
    print("  [PASS] Notification sent to graduated student")


def test_command_tutup_generasi_flow():
    print("\n--- 5. Testing /tutup_generasi Command ---")
    db, conn = setup_test_db()
    now = time.time()
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")

    # Seed 1 student
    prof = {
        "full_name": "Galang Pradana",
        "faculty": "f_teknik",
        "major": "jur_ti",
        "student_id": "2004030015",
        "class_enrolled": ["ti_dasar"],
        "total_sks": 21,
    }
    run_sync(
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (401, "galang", "Galang", ROLE_STUDENT, json.dumps(prof), now, now),
        )
    )
    run_sync(conn.commit())

    ctx = MagicMock()
    ctx.application.bot_data = {"conn": conn, "db": db}
    ctx.bot.send_message = AsyncMock()

    # Step A: Run without confirmation -> guidance and preview
    ctx.args = []
    up_preview = make_mock_update(owner_user, "/generasi_tutup")
    run_sync(commands.cmd_generasi_tutup(up_preview, ctx))
    preview_text = up_preview.message.reply_text.call_args[0][0]
    assert "Penutupan Generasi Akademik (Tutup Generasi)" in preview_text
    assert "Saat ini terdapat <b>1</b> mahasiswa aktif" in preview_text
    assert "/generasi_tutup konfirmasi" in preview_text
    print("  [PASS] /generasi_tutup without args shows active student count and guidance")

    # Step B: Run with confirmation -> executes mass rollover
    ctx.args = ["konfirmasi"]
    up_exec = make_mock_update(owner_user, "/generasi_tutup konfirmasi")
    run_sync(commands.cmd_generasi_tutup(up_exec, ctx))
    exec_text = up_exec.message.reply_text.call_args[0][0]
    assert "Transisi Massal ke Purna Shishya Selesai" in exec_text
    assert "Galang Pradana" in exec_text
    print("  [PASS] /generasi_tutup konfirmasi completed mass transition")

    # Verify user 401 is now purna with NIM intact
    r401 = run_sync(conn.execute("SELECT role, profile_json FROM users WHERE telegram_id = 401"))
    row401 = run_sync(r401.fetchone())
    assert row401["role"] == ROLE_PURNA
    p401 = json.loads(row401["profile_json"])
    assert p401["student_id"] == "2004030015"
    assert p401["accumulated_sks"] == 21
    print("  [PASS] User 401 successfully transitioned to Purna with NIM preserved")


def test_self_service_academic_documents_for_purna():
    print("\n--- 6. Testing Self-Service /transkrip & /ijazah for Purna ---")
    db, conn = setup_test_db()
    now = time.time()

    # User 501 is Purna with preserved NIM
    prof = {
        "full_name": "Aluna Sagita",
        "student_id": "2004010093",
        "accumulated_sks": 24,
        "total_sks": 24,
    }
    run_sync(
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, role, profile_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (501, "aluna", "Aluna", ROLE_PURNA, json.dumps(prof), now, now),
        )
    )
    run_sync(conn.commit())

    # Test _find_student with purna profile
    purna_user = make_mock_user(501, "aluna", "Aluna", ROLE_PURNA)
    urow = {"telegram_id": 501, "username": "aluna", "role": ROLE_PURNA}

    st = graduation._find_student(target_str="", profile=prof, row=urow, is_admin=False)
    assert st is not None, "Purna student must be found via their preserved NIM!"
    assert "2004010093" in st.nim
    print("  [PASS] Purna student successfully matched for academic document retrieval via NIM (2004010093)")


def main():
    print("==================================================================")
    print("STARTING TEST SUITE: MASS SETROLE PURNA & TUTUP GENERASI")
    print("==================================================================")
    test_parsing()
    test_security_guards()
    test_database_mass_set_role_purna()
    test_command_setrole_purna_all_flow()
    test_command_tutup_generasi_flow()
    test_self_service_academic_documents_for_purna()
    print("\n==================================================================")
    print("ALL TESTS PASSED! (6/6 Suites)")
    print("==================================================================")


if __name__ == "__main__":
    main()
