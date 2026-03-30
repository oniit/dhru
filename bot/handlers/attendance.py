from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import (
    ROLE_ADMIN,
    ROLE_LECTURER,
    ROLE_OWNER,
    role_can_open_presensi,
    role_can_report,
)
from bot.settings import CHOICES
from bot.timefmt import format_local_time

from .common import normalize_multi_choice_value, profile_from_row, user_row

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _class_label(class_id: str) -> str:
    for item in CHOICES.get("classes", []):
        if item.get("id") == class_id:
            return str(item.get("label", class_id))
    return class_id


def classes_for_presensi(profile: dict) -> list[str]:
    enrolled = normalize_multi_choice_value(profile.get("class_enrolled"))
    teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
    return list(dict.fromkeys(enrolled + teaching))


def can_rekap_hadir_session(row, profile: dict, session_class_id: str) -> bool:
    if role_can_report(row["role"]):
        return True
    if row["role"] == ROLE_LECTURER:
        teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
        return session_class_id in teaching
    return False


def _format_presensi_block(
    sess,
    records: list,
    *,
    closed: bool,
    show_record_times: bool,
) -> str:
    c_lab = _class_label(sess["class_id"])
    lines = [
        f"📋 *Presensi* `#{sess['id']}` — {c_lab}",
        f"Dibuka: {format_local_time(sess['opened_at'])}",
    ]
    closed_at = sess["closed_at"]
    if closed_at is not None:
        lines.append(f"Ditutup: {format_local_time(closed_at)}")
    if closed:
        lines.append("_Sesi ditutup._")
    else:
        lines.append("Ketuk *Hadir* atau gunakan perintah /hadir.")
    lines.append("")
    lines.append(f"*Hadir ({len(records)})*")
    if not records:
        lines.append("_Belum ada._")
    else:
        for r in records:
            pj = json.loads(r["profile_json"] or "{}")
            name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
            if show_record_times:
                lines.append(
                    f"• {name} — `{format_local_time(r['recorded_at'])}`"
                )
            else:
                lines.append(f"• {name}")
    return "\n".join(lines)


async def refresh_presensi_announcement(
    context: ContextTypes.DEFAULT_TYPE,
    db,
    conn,
    session_id: int,
) -> None:
    sess = await db.get_attendance_session(conn, session_id)
    if not sess or not sess["announce_message_id"] or not sess["chat_id"]:
        return
    _, records = await db.attendance_recap_session(conn, session_id)
    closed = sess["closed_at"] is not None
    text = _format_presensi_block(
        sess, records, closed=closed, show_record_times=False
    )
    kb = None
    if not closed:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Hadir", callback_data=f"h:{session_id}"[:32]
                    )
                ]
            ]
        )
    try:
        await context.bot.edit_message_text(
            chat_id=sess["chat_id"],
            message_id=sess["announce_message_id"],
            text=text[:4000],
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        log.debug("edit presensi message: %s", e)


async def _send_presensi_dm(context: ContextTypes.DEFAULT_TYPE, uid: int, text: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        log.warning("DM presensi ke %s: %s", uid, e)


def _classes_keyboard(allowed_class_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    rows = []
    allowed_set = set(allowed_class_ids) if allowed_class_ids is not None else None
    for item in CHOICES.get("classes", []):
        cid = item.get("id", "")
        if allowed_set is not None and cid not in allowed_set:
            continue
        lab = str(item.get("label", cid))
        rows.append([InlineKeyboardButton(lab, callback_data=f"o:{cid}"[:64])])
    return InlineKeyboardMarkup(rows)


async def cmd_buka_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not role_can_open_presensi(row["role"]):
        await update.message.reply_text("Hanya dosen/admin/owner yang bisa membuka presensi.")
        return
    profile = profile_from_row(row)
    allowed_class_ids: list[str] | None = None
    if row["role"] == ROLE_LECTURER:
        teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
        if not teaching:
            await update.message.reply_text(
                "Isi *Kelas yang diampu* di /lengkapi untuk membuka presensi.",
                parse_mode="Markdown",
            )
            return
        allowed_class_ids = teaching
    await update.message.reply_text(
        "Pilih kelas untuk sesi presensi:",
        reply_markup=_classes_keyboard(allowed_class_ids),
    )


async def cmd_tutup_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not role_can_open_presensi(row["role"]):
        await update.message.reply_text("Tidak diizinkan.")
        return
    parts = (update.message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("Pakai: `/tutup_presensi <id_sesi>`", parse_mode="Markdown")
        return
    sid = int(parts[1])
    sess = await db.get_attendance_session(conn, sid)
    if not sess:
        await update.message.reply_text("Sesi tidak ditemukan.")
        return
    if sess["closed_at"] is not None:
        await update.message.reply_text(
            f"Sesi `{sid}` sudah ditutup sebelumnya.",
            parse_mode="Markdown",
        )
        return
    opened_by = int(sess["opened_by"])
    await db.close_attendance_session(conn, sid)
    await db.add_audit(conn, update.effective_user.id, "presensi_close", f"session={sid}")
    sess2, records = await db.attendance_recap_session(conn, sid)
    recap_dm = _format_presensi_block(
        sess2, records, closed=True, show_record_times=True
    )
    recap_dm = f"📩 *Rekap presensi (DM)*\n\n{recap_dm}"
    await _send_presensi_dm(context, opened_by, recap_dm[:4000])
    # Admin/owner juga dapat rekap saat sesi ditutup.
    for mid in await db.list_moderator_telegram_ids(conn):
        if mid == opened_by:
            continue
        await _send_presensi_dm(context, mid, recap_dm[:4000])
    await refresh_presensi_announcement(context, db, conn, sid)
    await update.message.reply_text(f"Sesi `{sid}` ditutup.", parse_mode="Markdown")


async def cmd_hadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    profile = profile_from_row(row)
    user_classes = classes_for_presensi(profile)
    if not user_classes:
        await update.message.reply_text(
            "Lengkapi kelas di profil (/lengkapi) — mahasiswa: kelas diikuti; dosen: kelas diampu."
        )
        return
    sess = await db.get_open_session_for_classes(conn, user_classes)
    if not sess:
        await update.message.reply_text(
            "Tidak ada sesi presensi aktif untuk kelas yang relevan."
        )
        return
    ok, msg, added = await _record_hadir(
        db, conn, sess["id"], uid, row["role"], user_classes
    )
    await update.message.reply_text(msg)
    if ok:
        await refresh_presensi_announcement(context, db, conn, sess["id"])
        await _send_presensi_dm(context, uid, msg)


async def _record_hadir(
    db, conn, session_id: int, uid: int, role: str, user_classes: list[str]
):
    cur = await conn.execute(
        "SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)
    )
    sess = await cur.fetchone()
    if not sess or sess["closed_at"] is not None:
        return False, "Sesi tidak valid atau sudah ditutup.", False
    if (
        sess["class_id"] not in user_classes
        and role not in (ROLE_OWNER, ROLE_ADMIN)
    ):
        return False, "Sesi ini untuk kelas lain.", False
    added = await db.record_attendance(conn, session_id, uid)
    if added:
        return True, f"✅ Presensi kelas {_class_label(sess['class_id'])} tercatat. Terima kasih.", True
    return True, f"Kamu sudah tercatat hadir di sesi ini. Kelas: {_class_label(sess['class_id'])}.", False


async def cmd_sesi_aktif(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row:
        return
    profile = profile_from_row(row)
    if row["role"] == ROLE_LECTURER:
        teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
        if not teaching:
            await update.message.reply_text(
                "Isi *Kelas yang diampu* di /lengkapi untuk melihat sesi relevan.",
                parse_mode="Markdown",
            )
            return
    elif not role_can_report(row["role"]):
        await update.message.reply_text("Hanya admin/owner atau dosen (dengan kelas diampu).")
        return

    open_sess = await db.recent_open_sessions(conn, 20)
    if row["role"] == ROLE_LECTURER:
        teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
        open_sess = [s for s in open_sess if s["class_id"] in teaching]
    if not open_sess:
        await update.message.reply_text("Tidak ada sesi presensi aktif.")
        return
    lines = ["*Sesi presensi aktif*"]
    for s in open_sess:
        lines.append(
            f"• `#{s['id']}` {_class_label(s['class_id'])} — buka {format_local_time(s['opened_at'])}"
        )
    lines.append("\nTutup dengan `/tutup_presensi <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_rekap_hadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row:
        return
    profile = profile_from_row(row)
    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Pakai: `/rekap_hadir <id_sesi>` atau `/rekap_hadir all` atau `/rekap_hadir total`",
            parse_mode="Markdown",
        )
        return

    arg = parts[1]
    allowed_class_ids: list[str] | None = None
    if row["role"] == ROLE_LECTURER:
        teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
        if not teaching:
            await update.message.reply_text(
                "Isi *Kelas yang diampu* di /lengkapi untuk melihat rekap.",
                parse_mode="Markdown",
            )
            return
        allowed_class_ids = teaching

    if arg in ("all", "total"):
        # Lecturer hanya boleh lihat matkul yang dia ampu.
        if arg == "all":
            if allowed_class_ids is None:
                cur = await conn.execute(
                    """
                    SELECT id, class_id, opened_at, closed_at
                    FROM attendance_sessions
                    ORDER BY id DESC
                    """
                )
                sessions = await cur.fetchall()
            else:
                placeholders = ",".join("?" * len(allowed_class_ids))
                cur = await conn.execute(
                    f"""
                    SELECT id, class_id, opened_at, closed_at
                    FROM attendance_sessions
                    WHERE class_id IN ({placeholders})
                    ORDER BY id DESC
                    """,
                    allowed_class_ids,
                )
                sessions = await cur.fetchall()

            if not sessions:
                await update.message.reply_text("Belum ada sesi presensi.")
                return

            lines = ["*Rekap presensi (semua sesi)*"]
            for s in sessions:
                closed_at = s["closed_at"]
                lines.append(
                    f"• `#{s['id']}` {_class_label(s['class_id'])} — "
                    f"buka {format_local_time(s['opened_at'])}, "
                    f"tutup {format_local_time(closed_at) if closed_at else '—'}"
                )
            await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")
            return

        # arg == "total"
        if allowed_class_ids is None:
            cur = await conn.execute(
                """
                SELECT class_id, COUNT(*) as session_count
                FROM attendance_sessions
                WHERE closed_at IS NOT NULL
                GROUP BY class_id
                ORDER BY session_count DESC
                """
            )
            rows = await cur.fetchall()
        else:
            placeholders = ",".join("?" * len(allowed_class_ids))
            cur = await conn.execute(
                f"""
                SELECT class_id, COUNT(*) as session_count
                FROM attendance_sessions
                WHERE closed_at IS NOT NULL
                  AND class_id IN ({placeholders})
                GROUP BY class_id
                ORDER BY session_count DESC
                """,
                allowed_class_ids,
            )
            rows = await cur.fetchall()

        if not rows:
            await update.message.reply_text("Belum ada rekap sesi yang sudah ditutup.")
            return

        lines = ["*Rekap presensi per matkul (jumlah sesi ditutup)*"]
        for r in rows:
            lines.append(f"• {_class_label(r['class_id'])} — {int(r['session_count'])} sesi")
        await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")
        return

    if not arg.isdigit():
        await update.message.reply_text(
            "Pakai: `/rekap_hadir <id_sesi>` atau `/rekap_hadir all` atau `/rekap_hadir total`",
            parse_mode="Markdown",
        )
        return

    sid = int(arg)
    sess, records = await db.attendance_recap_session(conn, sid)
    if not sess:
        await update.message.reply_text("Sesi tidak ada.")
        return
    if not can_rekap_hadir_session(row, profile, sess["class_id"]):
        await update.message.reply_text(
            "Kamu tidak punya akses rekap untuk sesi ini (bukan admin/owner atau bukan dosen kelas tersebut)."
        )
        return
    lines = [
        f"*Rekap presensi* sesi `{sid}`",
        f"Kelas: {_class_label(sess['class_id'])}",
        f"Dibuka: {format_local_time(sess['opened_at'])}",
        f"Ditutup: {format_local_time(sess['closed_at']) if sess['closed_at'] else '— (aktif)'}",
        "",
        f"*Hadir ({len(records)} orang)*",
    ]
    for r in records:
        pj = profile_from_row(r)
        name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
        lines.append(
            f"• {name} — `{format_local_time(r['recorded_at'])}`"
        )
    await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")


async def cb_open_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user or not q.message:
        return
    await q.answer("Membuka sesi…")
    class_id = q.data.split(":", 1)[1]
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, q.from_user.id)
    if not row or not role_can_open_presensi(row["role"]):
        await q.edit_message_text("Tidak diizinkan.")
        return
    sid = await db.open_attendance_session(
        conn,
        class_id=class_id,
        title="",
        opened_by=q.from_user.id,
        chat_id=q.message.chat_id,
    )
    await db.add_audit(
        conn, q.from_user.id, "presensi_open", f"session={sid} class={class_id}"
    )
    sess = await db.get_attendance_session(conn, sid)
    _, records = await db.attendance_recap_session(conn, sid)
    text = _format_presensi_block(
        sess, records, closed=False, show_record_times=False
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Hadir", callback_data=f"h:{sid}"[:32]
                )
            ]
        ]
    )
    await q.edit_message_text(
        text[:4000],
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await db.set_attendance_announce_message(
        conn, sid, q.message.message_id
    )


async def cb_hadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    sid_s = q.data.split(":", 1)[1]
    if not sid_s.isdigit():
        return
    sid = int(sid_s)
    conn = _conn(context)
    db = _db(context)
    uid = q.from_user.id
    row = await user_row(conn, db, uid)
    if not row:
        await q.answer("Ketik /start dulu.", show_alert=True)
        return
    profile = profile_from_row(row)
    user_classes = classes_for_presensi(profile)
    if not user_classes:
        await q.answer("Lengkapi kelas di profil.", show_alert=True)
        return
    ok, msg, _ = await _record_hadir(
        db, conn, sid, uid, row["role"], user_classes
    )
    if ok:
        await q.answer()
        await refresh_presensi_announcement(context, db, conn, sid)
        await _send_presensi_dm(context, uid, msg)
    else:
        await q.answer(msg, show_alert=True)
