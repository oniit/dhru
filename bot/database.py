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
ROLE_LECTURER = "lecturer"
ROLE_STAFF = "staff"
ROLE_STUDENT = "student"

ROLES_ORDER = (ROLE_OWNER, ROLE_ADMIN, ROLE_LECTURER, ROLE_STAFF, ROLE_STUDENT)


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
    if role != ROLE_STUDENT:
        out.pop("student_id", None)
        return out

    faculty_id = str(out.get("faculty") or "").strip()
    major_id = str(out.get("major") or "").strip()
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
    return ROLE_STUDENT


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
    role TEXT NOT NULL DEFAULT 'student',
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
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
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

CREATE TABLE IF NOT EXISTS group_seen_users (
    chat_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    last_seen_at REAL NOT NULL,
    PRIMARY KEY (chat_id, telegram_id)
);

CREATE INDEX IF NOT EXISTS idx_agra_target ON agra_ledger(target_telegram_id);
CREATE INDEX IF NOT EXISTS idx_pending_profile ON profile_change_requests(status);
CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance_records(session_id);
"""


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.executescript(SCHEMA)
        cur = await conn.execute("PRAGMA table_info(attendance_sessions)")
        cols = {str(r[1]) for r in await cur.fetchall()}
        if "announce_message_id" not in cols:
            await conn.execute(
                "ALTER TABLE attendance_sessions ADD COLUMN announce_message_id INTEGER"
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

    async def get_attendance_session(
        self, conn: aiosqlite.Connection, session_id: int
    ) -> aiosqlite.Row | None:
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
        self, conn: aiosqlite.Connection, session_id: int, telegram_id: int
    ) -> bool:
        try:
            await conn.execute(
                """
                INSERT INTO attendance_records (session_id, telegram_id, recorded_at)
                VALUES (?, ?, ?)
                """,
                (session_id, telegram_id, time.time()),
            )
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

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
            INSERT INTO group_seen_users (
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
            FROM group_seen_users
            WHERE chat_id = ? AND is_bot = 0
            ORDER BY last_seen_at DESC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [int(r["telegram_id"]) for r in rows]

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
        class_id: str | None = None,
        name_substring: str | None = None,
    ) -> list[int]:
        cur = await conn.execute("SELECT telegram_id, profile_json FROM users")
        rows = await cur.fetchall()
        out: list[int] = []
        for r in rows:
            p = json.loads(r["profile_json"] or "{}")
            if faculty_id and p.get("faculty") != faculty_id:
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


def role_can_assign_roles(role: str) -> bool:
    return role == ROLE_OWNER


def role_can_approve_profile(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def role_can_view_sensitive_logs(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def role_can_add_agra(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN, ROLE_LECTURER)


def role_can_open_presensi(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN, ROLE_LECTURER)


def role_can_report(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def role_can_tag_all(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN, ROLE_STAFF, ROLE_LECTURER)


__all__ = [
    "Database",
    "DB_PATH",
    "ROLE_OWNER",
    "ROLE_ADMIN",
    "ROLE_LECTURER",
    "ROLE_STAFF",
    "ROLE_STUDENT",
    "role_can_assign_roles",
    "role_can_approve_profile",
    "role_can_view_sensitive_logs",
    "role_can_add_agra",
    "role_can_open_presensi",
    "role_can_report",
    "role_can_tag_all",
]
