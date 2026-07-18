"""SQLite persistence (async)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiosqlite

from bot.settings import ADMIN_IDS, CHOICES, OWNER_ID

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "bot.db"


ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_INTERNAL = "internal"
ROLE_STUDENT = "student"
ROLE_BEM = "bem"
ROLE_PUBLIC = "public"

ROLES_ORDER = (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL, ROLE_BEM, ROLE_STUDENT, ROLE_PUBLIC)


def _choice_position_code(choices_key: str, choice_id: str, width: int) -> str | None:
    for idx, item in enumerate(CHOICES.get(choices_key, []), start=1):
        if str(item.get("id")) == choice_id:
            return f"{idx:0{width}d}"
    return None


async def _start_order_code(
    conn: aiosqlite.Connection, telegram_id: int
) -> str | None:
    cur = await conn.execute(
        "SELECT created_at FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    created_at = row["created_at"]
    cur = await conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM users
        WHERE created_at < ? OR (created_at = ? AND telegram_id <= ?)
        """,
        (created_at, created_at, telegram_id),
    )
    rank_row = await cur.fetchone()
    return f"{int(rank_row['n'] or 0):04d}"


async def _apply_generated_profile_fields(
    conn: aiosqlite.Connection,
    telegram_id: int,
    role: str,
    profile: dict,
) -> dict:
    out = dict(profile)

    def _normalize_multi_choice(raw) -> list[str]:
        if isinstance(raw, list):
            return [str(x) for x in raw if x is not None and str(x).strip()]
        if isinstance(raw, str) and raw.strip():
            return [raw.strip()]
        return []

    # Calc SKS: kelas otomatis dari jurusan + kelas manual + club/UKM.
    major_id = str(out.get("major") or "").strip()
    enrolled_class_ids: set[str] = set(_normalize_multi_choice(out.get("class_enrolled")))
    for item in CHOICES.get("classes", []):
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue
        item_major = str(item.get("majors") or "").strip()
        if not item_major or (major_id and item_major == major_id):
            enrolled_class_ids.add(cid)

    sks_total = 0
    for item in CHOICES.get("classes", []):
        cid = str(item.get("id") or "").strip()
        if cid and cid in enrolled_class_ids:
            sks_total += int(item.get("sks", 0) or 0)

    enrolled_club_ids = set(_normalize_multi_choice(out.get("club_enrolled")))
    for item in CHOICES.get("clubs", []):
        cid = str(item.get("id") or "").strip()
        if cid and cid in enrolled_club_ids:
            sks_total += int(item.get("sks", 0) or 0)

    accumulated = int(out.get("accumulated_sks", 0))
    out["total_sks"] = accumulated + sks_total

    if role not in (ROLE_STUDENT, ROLE_BEM):
        out.pop("student_id", None)
        return out

    faculty_id = str(out.get("faculty") or "").strip()
    if not faculty_id or not major_id:
        out.pop("student_id", None)
        return out

    faculty_code = _choice_position_code("faculties", faculty_id, 2)
    major_code = _choice_position_code("majors", major_id, 3)
    start_order_code = await _start_order_code(conn, telegram_id)
    if not faculty_code or not major_code or not start_order_code:
        out.pop("student_id", None)
        return out

    out["student_id"] = f"{faculty_code}{major_code}01{start_order_code}"
    return out


def _initial_role_for_telegram_id(tg_id: int) -> str:
    if OWNER_ID and tg_id == OWNER_ID:
        return ROLE_OWNER
    if tg_id in ADMIN_IDS:
        return ROLE_ADMIN
    return ROLE_PUBLIC


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT,
    is_premium INTEGER DEFAULT 0,
    is_bot INTEGER DEFAULT 0,
    raw_profile_json TEXT,
    role TEXT NOT NULL DEFAULT 'public',
    profile_json TEXT NOT NULL DEFAULT '{}',
    onboarding_step TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    proposed_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    decided_at REAL,
    decided_by INTEGER,
    moderator_prompt_text TEXT,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS profile_request_mod_messages (
    request_id INTEGER NOT NULL,
    mod_chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (request_id, mod_chat_id),
    FOREIGN KEY (request_id) REFERENCES profile_change_requests(id)
);

CREATE TABLE IF NOT EXISTS agra_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_telegram_id INTEGER NOT NULL,
    actor_telegram_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    description TEXT NOT NULL,
    chat_id INTEGER,
    message_id INTEGER,
    created_at REAL NOT NULL,
    FOREIGN KEY (target_telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id TEXT NOT NULL,
    title TEXT,
    opened_by INTEGER NOT NULL,
    chat_id INTEGER,
    opened_at REAL NOT NULL,
    closed_at REAL,
    announce_message_id INTEGER,
    FOREIGN KEY (opened_by) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    recorded_at REAL NOT NULL,
    UNIQUE(session_id, telegram_id),
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agra_target ON agra_ledger(target_telegram_id);
CREATE INDEX IF NOT EXISTS idx_pending_profile ON profile_change_requests(status);
CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance_records(session_id);

CREATE TABLE IF NOT EXISTS access_codes (
    code TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    used_by INTEGER,
    used_at REAL,
    target_role TEXT NOT NULL DEFAULT 'student'
);

CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    created_by INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_chats (
    chat_id INTEGER PRIMARY KEY,
    type TEXT,
    title TEXT,
    is_active INTEGER DEFAULT 1,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS task_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at REAL NOT NULL,
    is_open INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (created_by) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS task_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    reject_reason TEXT,
    channel_message_id INTEGER,
    reviewed_by INTEGER,
    submitted_at REAL NOT NULL,
    reviewed_at REAL,
    UNIQUE(task_id, student_id),
    FOREIGN KEY (task_id) REFERENCES task_assignments(id),
    FOREIGN KEY (student_id) REFERENCES users(telegram_id)
);

CREATE INDEX IF NOT EXISTS idx_task_class ON task_assignments(class_id);
CREATE INDEX IF NOT EXISTS idx_task_sub ON task_submissions(task_id);
"""


TAGALL_SCHEMA = """
CREATE TABLE IF NOT EXISTS tagall.group_seen_users (
    chat_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    last_seen_at REAL NOT NULL,
    PRIMARY KEY (chat_id, telegram_id)
);
"""


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        
        tagall_path = self.path.parent / "tagall.db"
        await conn.execute(f"ATTACH DATABASE '{tagall_path}' AS tagall")
        
        await conn.executescript(SCHEMA)
        await conn.executescript(TAGALL_SCHEMA)
        
        try:
            await conn.execute("INSERT OR IGNORE INTO tagall.group_seen_users SELECT * FROM main.group_seen_users")
            await conn.execute("DROP TABLE main.group_seen_users")
        except Exception:
            pass
        cur = await conn.execute("PRAGMA table_info(attendance_sessions)")
        cols = {str(r[1]) for r in await cur.fetchall()}
        if "announce_message_id" not in cols:
            await conn.execute(
                "ALTER TABLE attendance_sessions ADD COLUMN announce_message_id INTEGER"
            )
        cur = await conn.execute("PRAGMA table_info(profile_change_requests)")
        pcr_cols = {str(r[1]) for r in await cur.fetchall()}
        if "moderator_prompt_text" not in pcr_cols:
            await conn.execute(
                "ALTER TABLE profile_change_requests ADD COLUMN moderator_prompt_text TEXT"
            )
        cur = await conn.execute("PRAGMA table_info(attendance_records)")
        rec_cols = {str(r[1]) for r in await cur.fetchall()}
        if "status" not in rec_cols:
            await conn.execute(
                "ALTER TABLE attendance_records ADD COLUMN status TEXT NOT NULL DEFAULT 'hadir'"
            )
        cur = await conn.execute("PRAGMA table_info(access_codes)")
        ac_cols = {str(r[1]) for r in await cur.fetchall()}
        if "target_role" not in ac_cols:
            await conn.execute(
                "ALTER TABLE access_codes ADD COLUMN target_role TEXT NOT NULL DEFAULT 'student'"
            )
        await conn.commit()
        return conn

    async def upsert_user_from_telegram(
        self,
        conn: aiosqlite.Connection,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        is_premium: bool,
        is_bot: bool,
        raw_profile: dict,
    ) -> None:
        now = time.time()
        cur = await conn.execute(
            "SELECT role FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        role = row["role"] if row else _initial_role_for_telegram_id(telegram_id)
        raw_json = json.dumps(raw_profile, ensure_ascii=False)
        if row:
            await conn.execute(
                """
                UPDATE users SET
                    username = ?, first_name = ?, last_name = ?,
                    language_code = ?, is_premium = ?, is_bot = ?,
                    raw_profile_json = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    language_code,
                    1 if is_premium else 0,
                    1 if is_bot else 0,
                    raw_json,
                    now,
                    telegram_id,
                ),
            )
        else:
            await conn.execute(
                """
                INSERT INTO users (
                    telegram_id, username, first_name, last_name, language_code,
                    is_premium, is_bot, raw_profile_json, role, profile_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    language_code,
                    1 if is_premium else 0,
                    1 if is_bot else 0,
                    raw_json,
                    role,
                    now,
                    now,
                ),
            )
        await conn.commit()

    async def get_user(self, conn: aiosqlite.Connection, telegram_id: int) -> aiosqlite.Row | None:
        cur = await conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return row

    async def get_profile_dict(self, conn: aiosqlite.Connection, telegram_id: int) -> dict:
        row = await self.get_user(conn, telegram_id)
        if not row:
            return {}
        return json.loads(row["profile_json"] or "{}")

    async def set_profile_partial(
        self, conn: aiosqlite.Connection, telegram_id: int, updates: dict
    ) -> None:
        current = await self.get_profile_dict(conn, telegram_id)
        current.update(updates)
        row = await self.get_user(conn, telegram_id)
        role = row["role"] if row else ROLE_STUDENT
        current = await _apply_generated_profile_fields(
            conn, telegram_id, role, current
        )
        now = time.time()
        await conn.execute(
            "UPDATE users SET profile_json = ?, updated_at = ? WHERE telegram_id = ?",
            (json.dumps(current, ensure_ascii=False), now, telegram_id),
        )
        await conn.commit()

    async def remove_profile_keys(
        self, conn: aiosqlite.Connection, telegram_id: int, keys: list[str]
    ) -> None:
        if not keys:
            return
        current = await self.get_profile_dict(conn, telegram_id)
        for k in keys:
            current.pop(k, None)
        row = await self.get_user(conn, telegram_id)
        role = row["role"] if row else ROLE_STUDENT
        current = await _apply_generated_profile_fields(
            conn, telegram_id, role, current
        )
        now = time.time()
        await conn.execute(
            "UPDATE users SET profile_json = ?, updated_at = ? WHERE telegram_id = ?",
            (json.dumps(current, ensure_ascii=False), now, telegram_id),
        )
        await conn.commit()

    async def set_onboarding_step(
        self, conn: aiosqlite.Connection, telegram_id: int, step: str | None
    ) -> None:
        now = time.time()
        await conn.execute(
            "UPDATE users SET onboarding_step = ?, updated_at = ? WHERE telegram_id = ?",
            (step, now, telegram_id),
        )
        await conn.commit()

    async def set_role(
        self, conn: aiosqlite.Connection, telegram_id: int, role: str
    ) -> None:
        current = await self.get_profile_dict(conn, telegram_id)
        current = await _apply_generated_profile_fields(
            conn, telegram_id, role, current
        )
        now = time.time()
        await conn.execute(
            "UPDATE users SET role = ?, profile_json = ?, updated_at = ? WHERE telegram_id = ?",
            (role, json.dumps(current, ensure_ascii=False), now, telegram_id),
        )
        await conn.commit()

    async def list_pending_profile_requests(
        self, conn: aiosqlite.Connection
    ) -> list[aiosqlite.Row]:
        cur = await conn.execute(
            """
            SELECT * FROM profile_change_requests
            WHERE status = 'pending' ORDER BY id ASC
            """
        )
        return await cur.fetchall()

    async def add_profile_request(
        self, conn: aiosqlite.Connection, telegram_id: int, proposed: dict
    ) -> int:
        now = time.time()
        cur = await conn.execute(
            """
            INSERT INTO profile_change_requests (telegram_id, proposed_json, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (telegram_id, json.dumps(proposed, ensure_ascii=False), now),
        )
        await conn.commit()
        return cur.lastrowid

    async def set_profile_request_moderator_prompt(
        self, conn: aiosqlite.Connection, request_id: int, text: str
    ) -> None:
        await conn.execute(
            """
            UPDATE profile_change_requests
            SET moderator_prompt_text = ?
            WHERE id = ?
            """,
            (text, request_id),
        )
        await conn.commit()

    async def register_profile_request_mod_message(
        self,
        conn: aiosqlite.Connection,
        request_id: int,
        mod_chat_id: int,
        message_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT OR REPLACE INTO profile_request_mod_messages
            (request_id, mod_chat_id, message_id)
            VALUES (?, ?, ?)
            """,
            (request_id, mod_chat_id, message_id),
        )
        await conn.commit()

    async def list_profile_request_mod_messages(
        self, conn: aiosqlite.Connection, request_id: int
    ) -> list[aiosqlite.Row]:
        cur = await conn.execute(
            """
            SELECT mod_chat_id, message_id
            FROM profile_request_mod_messages
            WHERE request_id = ?
            """,
            (request_id,),
        )
        return await cur.fetchall()

    async def get_profile_request(
        self, conn: aiosqlite.Connection, request_id: int
    ) -> aiosqlite.Row | None:
        cur = await conn.execute(
            "SELECT * FROM profile_change_requests WHERE id = ?", (request_id,)
        )
        return await cur.fetchone()

    async def resolve_profile_request(
        self,
        conn: aiosqlite.Connection,
        request_id: int,
        approve: bool,
        decided_by: int,
    ) -> tuple[bool, int | None, dict | None]:
        cur = await conn.execute(
            "SELECT * FROM profile_change_requests WHERE id = ?", (request_id,)
        )
        row = await cur.fetchone()
        if not row or row["status"] != "pending":
            return False, None, None
        now = time.time()
        tid = row["telegram_id"]
        proposed = json.loads(row["proposed_json"])
        if approve:
            user_row = await self.get_user(conn, tid)
            base = json.loads(user_row["profile_json"] or "{}")
            base.update(proposed)
            role = user_row["role"] if user_row else ROLE_STUDENT
            base = await _apply_generated_profile_fields(conn, tid, role, base)
            await conn.execute(
                "UPDATE users SET profile_json = ?, updated_at = ? WHERE telegram_id = ?",
                (json.dumps(base, ensure_ascii=False), now, tid),
            )
        await conn.execute(
            """
            UPDATE profile_change_requests
            SET status = ?, decided_at = ?, decided_by = ?
            WHERE id = ?
            """,
            ("approved" if approve else "rejected", now, decided_by, request_id),
        )
        await conn.commit()
        return True, tid, proposed

    async def add_audit(
        self,
        conn: aiosqlite.Connection,
        actor_id: int | None,
        action: str,
        detail: str | None = None,
    ) -> None:
        await conn.execute(
            "INSERT INTO audit_log (actor_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (actor_id, action, detail, time.time()),
        )
        await conn.commit()

    async def agra_total(self, conn: aiosqlite.Connection, telegram_id: int) -> int:
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM agra_ledger WHERE target_telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        return int(row["s"] or 0)

    async def add_agra(
        self,
        conn: aiosqlite.Connection,
        *,
        target_id: int,
        actor_id: int,
        amount: int,
        description: str,
        chat_id: int | None,
        message_id: int | None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO agra_ledger (
                target_telegram_id, actor_telegram_id, amount, description,
                chat_id, message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, actor_id, amount, description, chat_id, message_id, time.time()),
        )
        await conn.commit()

    async def agra_report(
        self, conn: aiosqlite.Connection, limit: int = 50
    ) -> list[aiosqlite.Row]:
        cur = await conn.execute(
            """
            SELECT l.*, u.username AS target_username, u.first_name AS target_first
            FROM agra_ledger l
            LEFT JOIN users u ON u.telegram_id = l.target_telegram_id
            ORDER BY l.id DESC LIMIT ?
            """,
            (limit,),
        )
        return await cur.fetchall()

    async def agra_report_user(
        self, conn: aiosqlite.Connection, telegram_id: int, limit: int = 50
    ) -> list[aiosqlite.Row]:
        cur = await conn.execute(
            """
            SELECT l.*, u.username AS target_username, u.first_name AS target_first
            FROM agra_ledger l
            LEFT JOIN users u ON u.telegram_id = l.target_telegram_id
            WHERE l.target_telegram_id = ?
            ORDER BY l.id DESC LIMIT ?
            """,
            (telegram_id, limit),
        )
        return await cur.fetchall()

    async def open_attendance_session(
        self,
        conn: aiosqlite.Connection,
        *,
        class_id: str,
        title: str | None,
        opened_by: int,
        chat_id: int | None,
    ) -> int:
        now = time.time()
        await conn.execute(
            """
            UPDATE attendance_sessions SET closed_at = ?
            WHERE class_id = ? AND closed_at IS NULL
            """,
            (now, class_id),
        )
        cur = await conn.execute(
            """
            INSERT INTO attendance_sessions (
                class_id, title, opened_by, chat_id, opened_at, announce_message_id
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (class_id, title or "", opened_by, chat_id, now),
        )
        await conn.commit()
        return cur.lastrowid

    async def close_attendance_session(
        self, conn: aiosqlite.Connection, session_id: int
    ) -> None:
        await conn.execute(
            "UPDATE attendance_sessions SET closed_at = ? WHERE id = ? AND closed_at IS NULL",
            (time.time(), session_id),
        )
        await conn.commit()

    async def _auto_close_stale_sessions(self, conn: aiosqlite.Connection) -> None:
        stale_cutoff = time.time() - 7200
        await conn.execute(
            "UPDATE attendance_sessions SET closed_at = opened_at + 7200 WHERE closed_at IS NULL AND opened_at < ? AND class_id != 'staff_auto'",
            (stale_cutoff,)
        )
        await conn.commit()

    async def get_attendance_session(
        self, conn: aiosqlite.Connection, session_id: int
    ) -> aiosqlite.Row | None:
        await self._auto_close_stale_sessions(conn)
        cur = await conn.execute(
            "SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)
        )
        return await cur.fetchone()

    async def set_attendance_announce_message(
        self,
        conn: aiosqlite.Connection,
        session_id: int,
        message_id: int | None,
    ) -> None:
        await conn.execute(
            "UPDATE attendance_sessions SET announce_message_id = ? WHERE id = ?",
            (message_id, session_id),
        )
        await conn.commit()

    async def get_open_session_for_class(
        self, conn: aiosqlite.Connection, class_id: str
    ) -> aiosqlite.Row | None:
        await self._auto_close_stale_sessions(conn)
        cur = await conn.execute(
            """
            SELECT * FROM attendance_sessions
            WHERE class_id = ? AND closed_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (class_id,),
        )
        return await cur.fetchone()

    async def get_open_session_for_classes(
        self, conn: aiosqlite.Connection, class_ids: list[str]
    ) -> aiosqlite.Row | None:
        await self._auto_close_stale_sessions(conn)
        if not class_ids:
            return None
        placeholders = ",".join("?" * len(class_ids))
        cur = await conn.execute(
            f"""
            SELECT * FROM attendance_sessions
            WHERE class_id IN ({placeholders}) AND closed_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            class_ids,
        )
        return await cur.fetchone()

    async def record_attendance(
        self, conn: aiosqlite.Connection, session_id: int, telegram_id: int, status: str = "hadir"
    ) -> tuple[bool, str]:
        cur = await conn.execute(
            "SELECT status FROM attendance_records WHERE session_id = ? AND telegram_id = ?",
            (session_id, telegram_id)
        )
        row = await cur.fetchone()
        if not row:
            await conn.execute(
                """
                INSERT INTO attendance_records (session_id, telegram_id, recorded_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, telegram_id, time.time(), status),
            )
            await conn.commit()
            return True, ""
        else:
            old_status = row["status"]
            if old_status == status:
                return False, old_status
            await conn.execute(
                "UPDATE attendance_records SET status = ?, recorded_at = ? WHERE session_id = ? AND telegram_id = ?",
                (status, time.time(), session_id, telegram_id)
            )
            await conn.commit()
            return True, old_status

    async def attendance_recap_session(
        self, conn: aiosqlite.Connection, session_id: int
    ) -> tuple[aiosqlite.Row | None, list[aiosqlite.Row]]:
        cur = await conn.execute(
            "SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)
        )
        sess = await cur.fetchone()
        cur = await conn.execute(
            """
            SELECT r.*, u.username, u.first_name, u.profile_json
            FROM attendance_records r
            JOIN users u ON u.telegram_id = r.telegram_id
            WHERE r.session_id = ?
            ORDER BY r.recorded_at ASC
            """,
            (session_id,),
        )
        rows = await cur.fetchall()
        return sess, rows

    async def recent_open_sessions(
        self, conn: aiosqlite.Connection, limit: int = 10
    ) -> list[aiosqlite.Row]:
        await self._auto_close_stale_sessions(conn)
        cur = await conn.execute(
            """
            SELECT * FROM attendance_sessions WHERE closed_at IS NULL
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        return await cur.fetchall()

    async def list_moderator_telegram_ids(
        self, conn: aiosqlite.Connection
    ) -> list[int]:
        cur = await conn.execute(
            """
            SELECT telegram_id FROM users
            WHERE role IN (?, ?) ORDER BY telegram_id
            """,
            (ROLE_OWNER, ROLE_ADMIN),
        )
        rows = await cur.fetchall()
        return [int(r["telegram_id"]) for r in rows]

    async def get_all_staff_ids(
        self, conn: aiosqlite.Connection
    ) -> list[int]:
        cur = await conn.execute(
            """
            SELECT telegram_id FROM users
            WHERE role = ? ORDER BY telegram_id
            """,
            ("internal",),
        )
        rows = await cur.fetchall()
        return [int(r["telegram_id"]) for r in rows]

    async def find_ids_by_usernames(
        self, conn: aiosqlite.Connection, usernames: list[str]
    ) -> list[int]:
        if not usernames:
            return []
        lowered = [u.lower().lstrip("@") for u in usernames]
        placeholders = ",".join("?" * len(lowered))
        cur = await conn.execute(
            f"""
            SELECT telegram_id FROM users
            WHERE lower(username) IN ({placeholders})
            """,
            lowered,
        )
        rows = await cur.fetchall()
        return [int(r["telegram_id"]) for r in rows]

    async def reset_academic_period(self, conn: aiosqlite.Connection) -> dict[str, int]:
        """
        Reset periode akademik:
        1. Bank SKS: accumulated_sks += current total_sks untuk student/bem.
        2. Reset role student/bem ke public & hapus field period-specific.
        3. Hapus agra_ledger, attendance_records, attendance_sessions.
        """
        # 1. Update users
        cur = await conn.execute("SELECT telegram_id, role, profile_json FROM users")
        rows = await cur.fetchall()
        user_updates = 0
        for row in rows:
            uid = row["telegram_id"]
            role = row["role"]
            if role not in (ROLE_STUDENT, ROLE_BEM):
                continue
            
            prof = json.loads(row["profile_json"] or "{}")
            # Bank SKS
            current_total = int(prof.get("total_sks", 0))
            prof["accumulated_sks"] = current_total
            
            # Clear period-specific fields
            for k in ["class_enrolled", "club_enrolled", "faculty", "major", "bem_position"]:
                prof.pop(k, None)
            
            # Recalculate (will result in accumulated_sks since other fields are gone)
            prof = await _apply_generated_profile_fields(conn, uid, ROLE_PUBLIC, prof)
            
            await conn.execute(
                "UPDATE users SET role = ?, profile_json = ?, onboarding_step = NULL, updated_at = ? WHERE telegram_id = ?",
                (ROLE_PUBLIC, json.dumps(prof, ensure_ascii=False), time.time(), uid)
            )
            user_updates += 1
            
        # 2. Clear tables
        cur = await conn.execute("DELETE FROM agra_ledger")
        agra_count = cur.rowcount
        cur = await conn.execute("DELETE FROM attendance_records")
        att_rec_count = cur.rowcount
        cur = await conn.execute("DELETE FROM attendance_sessions")
        att_sess_count = cur.rowcount
        cur = await conn.execute("DELETE FROM task_submissions")
        task_sub_count = cur.rowcount
        cur = await conn.execute("DELETE FROM task_assignments")
        task_assign_count = cur.rowcount
        
        await conn.commit()
        return {
            "users_reset_to_public": user_updates,
            "agra_records_deleted": agra_count,
            "attendance_records_deleted": att_rec_count,
            "attendance_sessions_deleted": att_sess_count,
            "task_submissions_deleted": task_sub_count,
            "task_assignments_deleted": task_assign_count
        }

    async def touch_group_seen_user(
        self,
        conn: aiosqlite.Connection,
        *,
        chat_id: int,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        is_bot: bool,
    ) -> None:
        now = time.time()
        await conn.execute(
            """
            INSERT INTO tagall.group_seen_users (
                chat_id, telegram_id, username, first_name, last_name, is_bot, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                is_bot = excluded.is_bot,
                last_seen_at = excluded.last_seen_at
            """,
            (
                chat_id,
                telegram_id,
                username,
                first_name,
                last_name,
                1 if is_bot else 0,
                now,
            ),
        )
        await conn.commit()

    async def list_group_seen_user_ids(
        self, conn: aiosqlite.Connection, chat_id: int
    ) -> list[int]:
        cur = await conn.execute(
            """
            SELECT telegram_id
            FROM tagall.group_seen_users
            WHERE chat_id = ? AND is_bot = 0
            ORDER BY last_seen_at DESC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [int(r["telegram_id"]) for r in rows]

    async def upsert_bot_chat(
        self, conn: aiosqlite.Connection, chat_id: int, chat_type: str, title: str, is_active: bool
    ) -> None:
        await conn.execute(
            """
            INSERT INTO bot_chats (chat_id, type, title, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                type = excluded.type,
                title = excluded.title,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (chat_id, chat_type, title, 1 if is_active else 0, time.time())
        )
        await conn.commit()

    async def list_active_bot_chats(
        self, conn: aiosqlite.Connection, chat_type: str = "group"
    ) -> list[tuple[int, str]]:
        if chat_type == "group":
            query = "SELECT chat_id, title FROM bot_chats WHERE is_active = 1 AND type IN ('group', 'supergroup')"
        else:
            query = f"SELECT chat_id, title FROM bot_chats WHERE is_active = 1 AND type = '{chat_type}'"
            
        cur = await conn.execute(query)
        rows = await cur.fetchall()
        return [(int(r["chat_id"]), r["title"]) for r in rows]

    # ── Task Assignment Methods ──────────────────────────────────────

    async def create_task(
        self, conn: aiosqlite.Connection, *, class_id: str, title: str, created_by: int
    ) -> int:
        now = time.time()
        cur = await conn.execute(
            """
            INSERT INTO task_assignments (class_id, title, created_by, created_at, is_open)
            VALUES (?, ?, ?, ?, 1)
            """,
            (class_id, title, created_by, now),
        )
        await conn.commit()
        return cur.lastrowid

    async def get_task(self, conn: aiosqlite.Connection, task_id: int) -> aiosqlite.Row | None:
        cur = await conn.execute("SELECT * FROM task_assignments WHERE id = ?", (task_id,))
        return await cur.fetchone()

    async def list_tasks_for_classes(
        self, conn: aiosqlite.Connection, class_ids: list[str], only_open: bool = True
    ) -> list[aiosqlite.Row]:
        if not class_ids:
            return []
        ph = ",".join("?" * len(class_ids))
        where = f"class_id IN ({ph})"
        if only_open:
            where += " AND is_open = 1"
        cur = await conn.execute(
            f"SELECT * FROM task_assignments WHERE {where} ORDER BY created_at DESC",
            class_ids,
        )
        return await cur.fetchall()

    async def list_tasks_by_lecturer(
        self, conn: aiosqlite.Connection, lecturer_id: int, only_open: bool = False
    ) -> list[aiosqlite.Row]:
        if only_open:
            cur = await conn.execute(
                "SELECT * FROM task_assignments WHERE created_by = ? AND is_open = 1 ORDER BY created_at DESC",
                (lecturer_id,),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM task_assignments WHERE created_by = ? ORDER BY created_at DESC",
                (lecturer_id,),
            )
        return await cur.fetchall()

    async def submit_task(
        self, conn: aiosqlite.Connection, *, task_id: int, student_id: int, content: str
    ) -> int:
        now = time.time()
        # Upsert: if rejected or already submitted (not accepted), allow resubmit
        cur = await conn.execute(
            "SELECT id, status FROM task_submissions WHERE task_id = ? AND student_id = ?",
            (task_id, student_id),
        )
        existing = await cur.fetchone()
        if existing:
            if existing["status"] == "accepted":
                return -1  # already accepted, cannot resubmit
            await conn.execute(
                """
                UPDATE task_submissions
                SET content = ?, status = 'submitted', reject_reason = NULL,
                    channel_message_id = NULL, reviewed_by = NULL,
                    submitted_at = ?, reviewed_at = NULL
                WHERE id = ?
                """,
                (content, now, existing["id"]),
            )
            await conn.commit()
            return int(existing["id"])
        cur = await conn.execute(
            """
            INSERT INTO task_submissions (task_id, student_id, content, status, submitted_at)
            VALUES (?, ?, ?, 'submitted', ?)
            """,
            (task_id, student_id, content, now),
        )
        await conn.commit()
        return cur.lastrowid

    async def get_submission(
        self, conn: aiosqlite.Connection, submission_id: int
    ) -> aiosqlite.Row | None:
        cur = await conn.execute("SELECT * FROM task_submissions WHERE id = ?", (submission_id,))
        return await cur.fetchone()

    async def get_submission_by_task_student(
        self, conn: aiosqlite.Connection, task_id: int, student_id: int
    ) -> aiosqlite.Row | None:
        cur = await conn.execute(
            "SELECT * FROM task_submissions WHERE task_id = ? AND student_id = ?",
            (task_id, student_id),
        )
        return await cur.fetchone()

    async def list_submissions_for_task(
        self, conn: aiosqlite.Connection, task_id: int
    ) -> list[aiosqlite.Row]:
        cur = await conn.execute(
            """
            SELECT ts.*, u.username, u.first_name, u.profile_json
            FROM task_submissions ts
            JOIN users u ON u.telegram_id = ts.student_id
            WHERE ts.task_id = ?
            ORDER BY ts.submitted_at DESC
            """,
            (task_id,),
        )
        return await cur.fetchall()

    async def review_submission(
        self,
        conn: aiosqlite.Connection,
        submission_id: int,
        *,
        accept: bool,
        reviewed_by: int,
        reason: str | None = None,
    ) -> bool:
        cur = await conn.execute(
            "SELECT * FROM task_submissions WHERE id = ?", (submission_id,)
        )
        row = await cur.fetchone()
        if not row or row["status"] == "accepted":
            return False
        now = time.time()
        status = "accepted" if accept else "rejected"
        await conn.execute(
            """
            UPDATE task_submissions
            SET status = ?, reviewed_by = ?, reviewed_at = ?, reject_reason = ?
            WHERE id = ?
            """,
            (status, reviewed_by, now, reason if not accept else None, submission_id),
        )
        await conn.commit()
        return True

    async def set_submission_channel_message(
        self, conn: aiosqlite.Connection, submission_id: int, message_id: int
    ) -> None:
        await conn.execute(
            "UPDATE task_submissions SET channel_message_id = ? WHERE id = ?",
            (message_id, submission_id),
        )
        await conn.commit()

    async def close_task(self, conn: aiosqlite.Connection, task_id: int) -> None:
        await conn.execute(
            "UPDATE task_assignments SET is_open = 0 WHERE id = ?", (task_id,)
        )
        await conn.commit()

    async def auto_close_stale_tasks(self, conn: aiosqlite.Connection) -> list[int]:
        """Close tasks older than 7 days. Returns list of closed task IDs."""
        cutoff = time.time() - 7 * 24 * 3600  # 1 week
        cur = await conn.execute(
            "SELECT id FROM task_assignments WHERE is_open = 1 AND created_at < ?",
            (cutoff,),
        )
        rows = await cur.fetchall()
        closed_ids = [int(r["id"]) for r in rows]
        if closed_ids:
            ph = ",".join("?" * len(closed_ids))
            await conn.execute(
                f"UPDATE task_assignments SET is_open = 0 WHERE id IN ({ph})",
                closed_ids,
            )
            await conn.commit()
        return closed_ids

    @staticmethod
    def _rowcount(cur: aiosqlite.Cursor) -> int:
        rc = getattr(cur, "rowcount", None)
        if rc is None or rc < 0:
            return 0
        return int(rc)

    async def reset_all_data_except_users(
        self, conn: aiosqlite.Connection
    ) -> dict[str, int]:
        """
        Reset data operasional bot (tanpa menghapus tabel/role user).
        Ini dirancang untuk keperluan owner saat debugging/maintenance.
        """
        # Order penting karena foreign key.
        cur = await conn.execute("DELETE FROM attendance_records")
        attendance_records = self._rowcount(cur)
        cur = await conn.execute("DELETE FROM attendance_sessions")
        attendance_sessions = self._rowcount(cur)

        cur = await conn.execute("DELETE FROM agra_ledger")
        agra_ledger = self._rowcount(cur)

        await conn.execute("DELETE FROM profile_request_mod_messages")
        cur = await conn.execute("DELETE FROM profile_change_requests")
        profile_change_requests = self._rowcount(cur)

        cur = await conn.execute("DELETE FROM audit_log")
        audit_log = self._rowcount(cur)

        cur = await conn.execute("DELETE FROM task_submissions")
        task_submissions = self._rowcount(cur)
        cur = await conn.execute("DELETE FROM task_assignments")
        task_assignments = self._rowcount(cur)

        await conn.commit()
        return {
            "attendance_records": attendance_records,
            "attendance_sessions": attendance_sessions,
            "agra_ledger": agra_ledger,
            "profile_change_requests": profile_change_requests,
            "audit_log": audit_log,
            "task_submissions": task_submissions,
            "task_assignments": task_assignments,
        }

    async def reset_attendance_all(
        self, conn: aiosqlite.Connection
    ) -> dict[str, int]:
        cur = await conn.execute("DELETE FROM attendance_records")
        attendance_records = self._rowcount(cur)
        cur = await conn.execute("DELETE FROM attendance_sessions")
        attendance_sessions = self._rowcount(cur)
        await conn.commit()
        return {
            "attendance_records": attendance_records,
            "attendance_sessions": attendance_sessions,
        }

    async def reset_attendance_for_user(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> dict[str, int]:
        """
        Reset data presensi yang terkait user:
        - hapus attendance_records yang tercatat user itu hadir
        - hapus sesi yang dibuka oleh user itu (termasuk record milik sesi tersebut)
        """
        cur = await conn.execute(
            "DELETE FROM attendance_records WHERE telegram_id = ?", (telegram_id,)
        )
        attendance_records_by_user = self._rowcount(cur)

        cur = await conn.execute(
            """
            DELETE FROM attendance_records
            WHERE session_id IN (
                SELECT id FROM attendance_sessions WHERE opened_by = ?
            )
            """,
            (telegram_id,),
        )
        attendance_records_for_opened_sessions = self._rowcount(cur)

        cur = await conn.execute(
            "DELETE FROM attendance_sessions WHERE opened_by = ?", (telegram_id,)
        )
        attendance_sessions_opened_by = self._rowcount(cur)
        await conn.commit()
        return {
            "attendance_records_by_user": attendance_records_by_user,
            "attendance_records_for_opened_sessions": attendance_records_for_opened_sessions,
            "attendance_sessions_opened_by": attendance_sessions_opened_by,
        }

    async def reset_attendance_for_class(
        self, conn: aiosqlite.Connection, class_id: str
    ) -> dict[str, int]:
        cur = await conn.execute(
            """
            DELETE FROM attendance_records
            WHERE session_id IN (
                SELECT id FROM attendance_sessions WHERE class_id = ?
            )
            """,
            (class_id,),
        )
        attendance_records = self._rowcount(cur)
        cur = await conn.execute(
            "DELETE FROM attendance_sessions WHERE class_id = ?", (class_id,)
        )
        attendance_sessions = self._rowcount(cur)
        await conn.commit()
        return {
            "attendance_records": attendance_records,
            "attendance_sessions": attendance_sessions,
        }

    async def reset_attendance_for_session(
        self, conn: aiosqlite.Connection, session_id: int
    ) -> dict[str, int]:
        cur = await conn.execute(
            "DELETE FROM attendance_records WHERE session_id = ?",
            (session_id,),
        )
        attendance_records = self._rowcount(cur)
        cur = await conn.execute(
            "DELETE FROM attendance_sessions WHERE id = ?",
            (session_id,),
        )
        attendance_sessions = self._rowcount(cur)
        await conn.commit()
        return {
            "attendance_records": attendance_records,
            "attendance_sessions": attendance_sessions,
        }

    async def reset_agra_all(self, conn: aiosqlite.Connection) -> int:
        cur = await conn.execute("DELETE FROM agra_ledger")
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_tasks_all(self, conn: aiosqlite.Connection) -> dict[str, int]:
        cur = await conn.execute("DELETE FROM task_submissions")
        subs = self._rowcount(cur)
        cur = await conn.execute("DELETE FROM task_assignments")
        tasks = self._rowcount(cur)
        await conn.commit()
        return {"task_submissions": subs, "task_assignments": tasks}

    async def reset_agra_for_user(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> int:
        cur = await conn.execute(
            """
            DELETE FROM agra_ledger
            WHERE target_telegram_id = ? OR actor_telegram_id = ?
            """,
            (telegram_id, telegram_id),
        )
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_profile_change_requests_all(self, conn: aiosqlite.Connection) -> int:
        await conn.execute("DELETE FROM profile_request_mod_messages")
        cur = await conn.execute("DELETE FROM profile_change_requests")
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_profile_change_requests_for_user(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> int:
        await conn.execute(
            """
            DELETE FROM profile_request_mod_messages
            WHERE request_id IN (
                SELECT id FROM profile_change_requests WHERE telegram_id = ?
            )
            """,
            (telegram_id,),
        )
        cur = await conn.execute(
            "DELETE FROM profile_change_requests WHERE telegram_id = ?",
            (telegram_id,),
        )
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_audit_log_all(self, conn: aiosqlite.Connection) -> int:
        cur = await conn.execute("DELETE FROM audit_log")
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_audit_log_for_user(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> int:
        cur = await conn.execute("DELETE FROM audit_log WHERE actor_id = ?", (telegram_id,))
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_group_seen_users_all(self, conn: aiosqlite.Connection) -> int:
        cur = await conn.execute("DELETE FROM tagall.group_seen_users")
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_group_seen_users_for_user(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> int:
        cur = await conn.execute(
            "DELETE FROM tagall.group_seen_users WHERE telegram_id = ?", (telegram_id,)
        )
        n = self._rowcount(cur)
        await conn.commit()
        return n

    async def reset_user_all_data(
        self, conn: aiosqlite.Connection, telegram_id: int
    ) -> dict[str, int]:
        """
        Reset data operasional bot yang terkait user (tanpa menghapus tabel users).
        """
        out: dict[str, int] = {}

        att = await self.reset_attendance_for_user(conn, telegram_id)
        out.update(att)

        out["agra_ledger"] = await self.reset_agra_for_user(conn, telegram_id)
        out["profile_change_requests"] = await self.reset_profile_change_requests_for_user(
            conn, telegram_id
        )
        out["audit_log"] = await self.reset_audit_log_for_user(conn, telegram_id)

        # Reset profil supaya user bisa /lengkapi lagi (seperti akun baru).
        # `group_seen_users` sengaja tidak dihapus agar data "seen" tetap ada.
        cur = await conn.execute(
            """
            UPDATE users
            SET profile_json = '{}',
                onboarding_step = NULL,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (time.time(), telegram_id),
        )
        out["users_profile_reset"] = self._rowcount(cur)

        cur = await conn.execute("DELETE FROM task_submissions WHERE student_id = ?", (telegram_id,))
        out["task_submissions"] = self._rowcount(cur)

        return out

    async def reset_all_users_all_data_except_env(
        self, conn: aiosqlite.Connection
    ) -> dict[str, int]:
        """
        Reset operasional "semua user" yang bukan OWNER_ID/ADMIN_IDS dari .env.
        `group_seen_users` sengaja tidak disentuh (biar seen tetap).
        """
        exclude_ids = [i for i in [OWNER_ID, *ADMIN_IDS] if i and int(i) != 0]
        placeholders = ",".join("?" * len(exclude_ids)) if exclude_ids else ""

        if not exclude_ids:
            cur = await conn.execute("SELECT telegram_id FROM users")
        else:
            cur = await conn.execute(
                f"SELECT telegram_id FROM users WHERE telegram_id NOT IN ({placeholders})",
                exclude_ids,
            )
        rows = await cur.fetchall()
        target_ids = [int(r["telegram_id"]) for r in rows]
        if not target_ids:
            return {"users_reset": 0}

        p = ",".join("?" * len(target_ids))
        now = time.time()

        cur = await conn.execute(
            f"DELETE FROM attendance_records WHERE telegram_id IN ({p})",
            target_ids,
        )
        attendance_records_by_user = self._rowcount(cur)

        cur = await conn.execute(
            f"""
            DELETE FROM attendance_records
            WHERE session_id IN (
                SELECT id FROM attendance_sessions WHERE opened_by IN ({p})
            )
            """,
            target_ids,
        )
        attendance_records_for_opened_sessions = self._rowcount(cur)

        cur = await conn.execute(
            f"DELETE FROM attendance_sessions WHERE opened_by IN ({p})",
            target_ids,
        )
        attendance_sessions_opened_by = self._rowcount(cur)

        cur = await conn.execute(
            f"""
            DELETE FROM agra_ledger
            WHERE target_telegram_id IN ({p})
               OR actor_telegram_id IN ({p})
            """,
            (*target_ids, *target_ids),
        )
        agra_ledger_deleted = self._rowcount(cur)

        cur = await conn.execute(
            f"""
            DELETE FROM profile_request_mod_messages
            WHERE request_id IN (
                SELECT id FROM profile_change_requests WHERE telegram_id IN ({p})
            )
            """,
            target_ids,
        )
        cur = await conn.execute(
            f"DELETE FROM profile_change_requests WHERE telegram_id IN ({p})",
            target_ids,
        )
        profile_change_requests_deleted = self._rowcount(cur)

        cur = await conn.execute(
            f"DELETE FROM audit_log WHERE actor_id IN ({p})",
            target_ids,
        )
        audit_log_deleted = self._rowcount(cur)

        cur = await conn.execute(
            f"""
            UPDATE users
            SET profile_json = '{{}}',
                onboarding_step = NULL,
                updated_at = ?
            WHERE telegram_id IN ({p})
            """,
            (now, *target_ids),
        )
        users_profile_reset = self._rowcount(cur)

        cur = await conn.execute(
            f"DELETE FROM task_submissions WHERE student_id IN ({p})",
            target_ids,
        )
        task_submissions_deleted = self._rowcount(cur)

        await conn.commit()

        return {
            "users_reset": len(target_ids),
            "attendance_records_by_user": attendance_records_by_user,
            "attendance_records_for_opened_sessions": attendance_records_for_opened_sessions,
            "attendance_sessions_opened_by": attendance_sessions_opened_by,
            "agra_ledger_deleted": agra_ledger_deleted,
            "profile_change_requests_deleted": profile_change_requests_deleted,
            "audit_log_deleted": audit_log_deleted,
            "users_profile_reset": users_profile_reset,
            "task_submissions_deleted": task_submissions_deleted,
        }

    async def ensure_owner_role(self, conn: aiosqlite.Connection) -> None:
        if not OWNER_ID:
            return
        await conn.execute(
            "UPDATE users SET role = ? WHERE telegram_id = ? AND role != ?",
            (ROLE_OWNER, OWNER_ID, ROLE_OWNER),
        )
        await conn.commit()

    async def user_ids_matching_profile_filter(
        self,
        conn: aiosqlite.Connection,
        *,
        faculty_id: str | None = None,
        major_id: str | None = None,
        class_id: str | None = None,
        ukm_id: str | None = None,
        name_substring: str | None = None,
    ) -> list[int]:
        cur = await conn.execute("SELECT telegram_id, profile_json FROM users")
        rows = await cur.fetchall()
        out: list[int] = []
        for r in rows:
            p = json.loads(r["profile_json"] or "{}")
            if faculty_id and p.get("faculty") != faculty_id:
                continue
            if major_id and p.get("major") != major_id:
                continue
            if class_id:
                raw = p.get("class_enrolled")
                enrolled: list[str] = []
                if isinstance(raw, list):
                    enrolled = [str(x) for x in raw if x is not None and str(x).strip()]
                elif isinstance(raw, str) and raw.strip():
                    enrolled = [raw.strip()]
                if class_id not in enrolled:
                    continue
            if ukm_id:
                raw = p.get("club_enrolled")
                enrolled: list[str] = []
                if isinstance(raw, list):
                    enrolled = [str(x) for x in raw if x is not None and str(x).strip()]
                elif isinstance(raw, str) and raw.strip():
                    enrolled = [raw.strip()]
                if ukm_id not in enrolled:
                    continue
            if name_substring:
                name = (p.get("full_name") or "").lower()
                if name_substring.lower() not in name:
                    continue
            out.append(int(r["telegram_id"]))
        return out

    async def audit_log_for_actors(
        self,
        conn: aiosqlite.Connection,
        actor_ids: list[int],
        limit: int = 20,
    ) -> list[aiosqlite.Row]:
        if not actor_ids:
            return []
        ph = ",".join("?" * len(actor_ids))
        cur = await conn.execute(
            f"""
            SELECT * FROM audit_log
            WHERE actor_id IN ({ph})
            ORDER BY id DESC LIMIT ?
            """,
            (*actor_ids, limit),
        )
        return await cur.fetchall()

    async def agra_ledger_for_targets(
        self,
        conn: aiosqlite.Connection,
        target_ids: list[int],
        limit: int = 15,
    ) -> list[aiosqlite.Row]:
        if not target_ids:
            return []
        ph = ",".join("?" * len(target_ids))
        cur = await conn.execute(
            f"""
            SELECT l.*, u.username AS target_username, u.first_name AS target_first
            FROM agra_ledger l
            LEFT JOIN users u ON u.telegram_id = l.target_telegram_id
            WHERE l.target_telegram_id IN ({ph})
            ORDER BY l.id DESC LIMIT ?
            """,
            (*target_ids, limit),
        )
        return await cur.fetchall()
    async def get_user_by_username_or_id(
        self, conn: aiosqlite.Connection, query: str
    ) -> aiosqlite.Row | None:
        if query.startswith("@"):
            username = query.lstrip("@").lower()
            cur = await conn.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (username,)
            )
            return await cur.fetchone()
        elif query.isdigit():
            return await self.get_user(conn, int(query))
        return None

    async def migrate_user_data(
        self, conn: aiosqlite.Connection, old_id: int, new_id: int
    ) -> bool:
        """
        Migrasi semua data dari old_id ke new_id.
        Jika new_id sudah terdaftar (sudah /start), kita ambil field-field dasarnya
        (seperti username, first_name) lalu hapus, sehingga kita bisa update old_id menjadi new_id.
        """
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (new_id,))
        new_user = await cur.fetchone()
        
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (old_id,))
        old_user = await cur.fetchone()
        if not old_user:
            return False # user lama tidak ditemukan
            
        username_new = new_user["username"] if new_user else None
        first_name_new = new_user["first_name"] if new_user else None
        last_name_new = new_user["last_name"] if new_user else None
        
        if new_user:
            # Delete new_id's existing operational data to avoid UNIQUE constraint conflicts
            await conn.execute("DELETE FROM attendance_records WHERE telegram_id = ?", (new_id,))
            await conn.execute("DELETE FROM attendance_records WHERE session_id IN (SELECT id FROM attendance_sessions WHERE opened_by = ?)", (new_id,))
            await conn.execute("DELETE FROM attendance_sessions WHERE opened_by = ?", (new_id,))
            await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id = ? OR actor_telegram_id = ?", (new_id, new_id))
            await conn.execute("DELETE FROM profile_request_mod_messages WHERE request_id IN (SELECT id FROM profile_change_requests WHERE telegram_id = ?)", (new_id,))
            await conn.execute("DELETE FROM profile_change_requests WHERE telegram_id = ?", (new_id,))
            await conn.execute("DELETE FROM task_submissions WHERE student_id = ?", (new_id,))
            await conn.execute("DELETE FROM task_assignments WHERE created_by = ?", (new_id,))
            await conn.execute("DELETE FROM audit_log WHERE actor_id = ?", (new_id,))
            await conn.execute("DELETE FROM tagall.group_seen_users WHERE telegram_id = ?", (new_id,))
            
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (new_id,))

        # Now migrate old_id to new_id
        await conn.execute(
            """
            UPDATE users SET 
                telegram_id = ?, 
                username = ?, 
                first_name = ?, 
                last_name = ?
            WHERE telegram_id = ?
            """,
            (new_id, username_new, first_name_new, last_name_new, old_id)
        )

        await conn.execute("UPDATE profile_change_requests SET telegram_id = ? WHERE telegram_id = ?", (new_id, old_id))
        await conn.execute("UPDATE agra_ledger SET target_telegram_id = ? WHERE target_telegram_id = ?", (new_id, old_id))
        await conn.execute("UPDATE agra_ledger SET actor_telegram_id = ? WHERE actor_telegram_id = ?", (new_id, old_id))
        await conn.execute("UPDATE attendance_sessions SET opened_by = ? WHERE opened_by = ?", (new_id, old_id))
        await conn.execute("UPDATE attendance_records SET telegram_id = ? WHERE telegram_id = ?", (new_id, old_id))
        await conn.execute("UPDATE task_assignments SET created_by = ? WHERE created_by = ?", (new_id, old_id))
        await conn.execute("UPDATE task_submissions SET student_id = ? WHERE student_id = ?", (new_id, old_id))
        await conn.execute("UPDATE audit_log SET actor_id = ? WHERE actor_id = ?", (new_id, old_id))
        await conn.execute("UPDATE tagall.group_seen_users SET telegram_id = ? WHERE telegram_id = ?", (new_id, old_id))
        
        await conn.commit()
        return True


__all__ = [
    "Database",
    "DB_PATH",
    "ROLE_OWNER",
    "ROLE_ADMIN",
    "ROLE_INTERNAL",
    "ROLE_BEM",
    "ROLE_STUDENT",
    "ROLE_PUBLIC",
]
