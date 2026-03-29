from __future__ import annotations

import json
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import (
    ROLE_ADMIN,
    ROLE_LECTURER,
    ROLE_OWNER,
    ROLE_STAFF,
    ROLE_STUDENT,
)
from bot.settings import (
    CHOICES,
    PROFILE_DISPLAY_KEYS,
    PROFILE_FIELDS,
    FieldDef,
    choice_label,
    field_applies_to_role,
    multi_choice_labels,
)

if TYPE_CHECKING:
    import aiosqlite

    from bot.database import Database


def role_display(role: str) -> str:
    return {
        ROLE_OWNER: "Founder",
        ROLE_ADMIN: "Sekretaris",
        ROLE_LECTURER: "Dosen / Coach",
        ROLE_STAFF: "Staf",
        ROLE_STUDENT: "Mahasiswa",
    }.get(role, role)


async def user_row(conn: aiosqlite.Connection, db: Database, telegram_id: int):
    return await db.get_user(conn, telegram_id)


def profile_from_row(row) -> dict:
    if not row:
        return {}
    return json.loads(row["profile_json"] or "{}")


def normalize_multi_choice_value(raw) -> list[str]:
    """Satu nilai string lama (choice tunggal) tetap didukung."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def field_label_for_key(field_key: str) -> str:
    fd = next((f for f in PROFILE_FIELDS if f.key == field_key), None)
    return fd.label if fd else field_key.replace("_", " ").title()


def fields_for_role(role: str) -> list[FieldDef]:
    return [
        f
        for f in PROFILE_FIELDS
        if field_applies_to_role(f, role) and f.key != "student_id" #yg baru and f.key != "student_id"
    ]


def display_keys_for_role(role: str) -> list[str]:
    out: list[str] = []
    for key in PROFILE_DISPLAY_KEYS:
        if key in ("telegram_name", "username"):
            continue
        if key in ("role", "agra_total"):
            out.append(key)
            continue
        fd = next((f for f in PROFILE_FIELDS if f.key == key), None)
        if fd:
            if field_applies_to_role(fd, role):
                out.append(key)
        else:
            out.append(key)
    return out


def missing_required_fields(profile: dict, role: str) -> list:
    miss = []
    for f in PROFILE_FIELDS:
        if not field_applies_to_role(f, role):
            continue
        if not f.required:
            continue
        v = profile.get(f.key)
        if f.type == "multi_choice":
            if not normalize_multi_choice_value(v):
                miss.append(f)
            continue
        if v is None or (isinstance(v, str) and not v.strip()):
            miss.append(f)
    return miss


def format_profile_card(
    row,
    *,
    profile: dict,
    agra: int,
    show_internal: bool,
    user_role: str,
) -> str:
    lines: list[str] = ["📇 *Profil*"]
    if not row:
        lines.append("_Belum terdaftar._")
        return "\n".join(lines)

    def val_for_display(key: str) -> str:
        if key == "telegram_name":
            fn = row["first_name"] or ""
            ln = row["last_name"] or ""
            return (fn + " " + ln).strip() or "—"
        if key == "username":
            u = row["username"]
            return f"@{u}" if u else "—"
        if key == "role":
            return role_display(row["role"])
        if key == "agra_total":
            return str(agra)
        fdef = next((x for x in PROFILE_FIELDS if x.key == key), None)
        if not fdef:
            return str(profile.get(key, "—"))
        raw = profile.get(fdef.key)
        if fdef.type == "multi_choice" and fdef.choices_key:
            return multi_choice_labels(fdef.choices_key, normalize_multi_choice_value(raw))
        if fdef.type == "choice" and fdef.choices_key:
            return choice_label(fdef.choices_key, raw) if raw else "—"
        return str(raw) if raw else "—"

    labels = {
        "telegram_name": "Nama Telegram",
        "username": "Username",
        "role": "Status",
        "agra_total": "Total Agra",
    }
    for key in display_keys_for_role(user_role):
        label = labels.get(key)
        if not label:
            fd = next((x for x in PROFILE_FIELDS if x.key == key), None)
            label = fd.label if fd else key.replace("_", " ").title()
        lines.append(f"*{label}:* {val_for_display(key)}")

    # raw_meta = json.loads(row["raw_profile_json"] or "{}")
    # if show_internal and raw_meta:
    #     lines.append("")
    #     lines.append("_Data mentah Telegram (hanya mod):_")
    #     for k, v in sorted(raw_meta.items()):
    #         if v is not None and v != "":
    #             lines.append(f"• `{k}`: `{v}`")

    return "\n".join(lines)


def keyboard_for_choices(
    field_key: str,
    choices_key: str,
    *,
    prefix: str = "lc",
    options: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    opts = options if options is not None else CHOICES.get(choices_key, [])
    rows = []
    row = []
    for i, item in enumerate(opts):
        cid = item.get("id", "")
        lab = str(item.get("label", cid))
        row.append(
            InlineKeyboardButton(
                lab, callback_data=f"{prefix}:{field_key}:{cid}"[:64]
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def keyboard_for_multi_choices(
    field_key: str,
    choices_key: str,
    selected: set[str],
    *,
    toggle_prefix: str,
    done_prefix: str,
) -> InlineKeyboardMarkup:
    opts = CHOICES.get(choices_key, [])
    rows: list[list[InlineKeyboardButton]] = []
    for item in opts:
        cid = str(item.get("id", ""))
        lab = str(item.get("label", cid))
        mark = "✓ " if cid in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    mark + lab,
                    callback_data=f"{toggle_prefix}:{field_key}:{cid}"[:64],
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "Selesai — simpan pilihan",
                callback_data=f"{done_prefix}:{field_key}"[:64],
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


async def sync_roles_from_env(db: Database, conn: aiosqlite.Connection) -> None:
    from bot.settings import ADMIN_IDS, OWNER_ID

    await db.ensure_owner_role(conn)
    if not OWNER_ID:
        return
    row = await db.get_user(conn, OWNER_ID)
    if row:
        await db.set_role(conn, OWNER_ID, ROLE_OWNER)
    for aid in ADMIN_IDS:
        r = await db.get_user(conn, aid)
        if r and r["role"] not in (ROLE_OWNER,):
            await db.set_role(conn, aid, ROLE_ADMIN)


async def moderator_chat_ids(db: Database, conn: aiosqlite.Connection) -> set[int]:
    from bot.settings import ADMIN_IDS, OWNER_ID

    ids = set(await db.list_moderator_telegram_ids(conn))
    if OWNER_ID:
        ids.add(OWNER_ID)
    ids |= ADMIN_IDS
    return ids


def is_lecturer_or_above(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN, ROLE_LECTURER)
