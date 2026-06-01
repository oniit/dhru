from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import (
    ROLE_ADMIN,
    ROLE_OWNER,
    ROLE_STUDENT,
)
from bot.settings import CHOICES
from bot.timefmt import TZ, format_local_time, format_time_only

from .common import (
    can_report,
    normalize_multi_choice_value,
    presence_allowed_class_ids,
    profile_from_row,
    user_row,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _class_label(class_id: str) -> str:
    items = CHOICES.get("classes", []) + CHOICES.get("clubs", [])
    for item in items:
        if item.get("id") == class_id:
            return str(item.get("label", class_id))
    return class_id


def get_automatic_classes(profile: dict) -> list[str]:
    major = profile.get("major")
    auto = []
    for item in CHOICES.get("classes", []):
        cid = item.get("id")
        m = item.get("majors")
        if not m:
            auto.append(cid)
        elif m == major:
            auto.append(cid)
    return auto


def classes_for_presensi(profile: dict) -> list[str]:
    enrolled = get_automatic_classes(profile)
    teaching = normalize_multi_choice_value(profile.get("teaching_classes"))
    return list(dict.fromkeys(enrolled + teaching))


def can_rekap_hadir_session(row, profile: dict, session_class_id: str) -> bool:
    if can_report(row["role"], profile):
        return True
    allowed = presence_allowed_class_ids(row["role"], profile)
    if allowed is None:
        return True
    return session_class_id in allowed


def _can_act_on_presensi(row, profile: dict) -> bool:
    allowed = presence_allowed_class_ids(row["role"], profile)
    return allowed is None or len(allowed) > 0


def _format_presensi_block(
    sess,
    records: list,
    *,
    closed: bool,
    show_record_times: bool,
) -> str:
    c_lab = _class_label(sess["class_id"])
    lines = [
        f"📋 <b>Presensi</b> <code>#{sess['id']}</code> — {c_lab}",
        f"Dibuka: {format_local_time(sess['opened_at'])}",
    ]
    closed_at = sess["closed_at"]
    if closed_at is not None:
        lines.append(f"Ditutup: {format_local_time(closed_at)}")
    if closed:
        lines.append("<i>Sesi ditutup.</i>")
    else:
        lines.append("Ketuk <b>Hadir</b> atau gunakan perintah /hadir.")
    lines.append("")
    hadir_records = [r for r in records if dict(r).get("status", "hadir") == "hadir"]
    izin_records = [r for r in records if dict(r).get("status", "hadir") == "izin"]

    lines.append(f"<b>Hadir ({len(hadir_records)})</b>")
    if not hadir_records:
        lines.append("<i>Belum ada.</i>")
    else:
        for r in hadir_records:
            pj = json.loads(r["profile_json"] or "{}")
            name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
            if show_record_times:
                lines.append(
                    f"• {name} — <code>{format_time_only(r['recorded_at'])}</code>"
                )
            else:
                lines.append(f"• {name}")
                
    lines.append("")
    lines.append(f"<b>Izin ({len(izin_records)})</b>")
    if not izin_records:
        lines.append("<i>Belum ada.</i>")
    else:
        for r in izin_records:
            pj = json.loads(r["profile_json"] or "{}")
            name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
            if show_record_times:
                lines.append(
                    f"• {name} — <code>{format_time_only(r['recorded_at'])}</code>"
                )
            else:
                lines.append(f"• {name}")
    return "\n".join(lines)


def format_local_date(ts: float | None) -> str:
    """Format tanggal saja (tanpa jam/WIB) untuk output ringkas."""
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(float(ts), tz=TZ)
    return dt.strftime("%d/%m")


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
                    ),
                    InlineKeyboardButton(
                        "⏸️ Izin", callback_data=f"i:{session_id}"[:32]
                    )
                ]
            ]
        )
    try:
        await context.bot.edit_message_text(
            chat_id=sess["chat_id"],
            message_id=sess["announce_message_id"],
            text=text[:4000],
            reply_markup=kb,
        )
    except Exception as e:
        log.debug("edit presensi message: %s", e)


async def _send_presensi_dm(context: ContextTypes.DEFAULT_TYPE, uid: int, text: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=text,
        )
    except Exception as e:
        log.warning("DM presensi ke %s: %s", uid, e)


def _classes_keyboard(allowed_class_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    rows = []
    allowed_set = set(allowed_class_ids) if allowed_class_ids is not None else None
    
    items = CHOICES.get("classes", []) + CHOICES.get("clubs", [])
    
    for item in items:
        cid = item.get("id", "")
        if allowed_set is not None and cid not in allowed_set:
            continue
        lab = str(item.get("label", cid))
        rows.append([InlineKeyboardButton(lab, callback_data=f"o:{cid}"[:64])])
    rows.append([InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")])
    return InlineKeyboardMarkup(rows)


async def cmd_buka_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    profile = profile_from_row(row) if row else {}
    if not row or not _can_act_on_presensi(row, profile):
        await update.message.reply_text(
            "Hanya dosen/admin/owner/cofounder, atau dekan staf (dengan fakultas lingkup), yang bisa membuka presensi."
        )
        return
    allowed_class_ids = presence_allowed_class_ids(row["role"], profile)
    if allowed_class_ids is not None and not allowed_class_ids:
        await update.message.reply_text(
            "Isi <b>Kelas yang diampu</b> dan/atau <b>Fakultas</b> di /lengkapi agar ada matkul untuk presensi.",
        )
        return
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
    profile = profile_from_row(row) if row else {}
    if not row or not _can_act_on_presensi(row, profile):
        await update.message.reply_text("Tidak diizinkan.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Pakai: <code>/presensi tutup &lt;id_sesi&gt;</code>")
        return
    sid = int(context.args[0])
    sess = await db.get_attendance_session(conn, sid)
    if not sess:
        await update.message.reply_text("Sesi tidak ditemukan.")
        return
    allowed = presence_allowed_class_ids(row["role"], profile)
    if allowed is not None and sess["class_id"] not in allowed:
        await update.message.reply_text(
            "Sesi ini untuk kelas di luar lingkup presensi kamu.",
        )
        return
    if sess["closed_at"] is not None:
        await update.message.reply_text(
            f"Sesi <code>{sid}</code> sudah ditutup sebelumnya.",
        )
        return
    opened_by = int(sess["opened_by"])
    await db.close_attendance_session(conn, sid)
    await db.add_audit(conn, update.effective_user.id, "presensi_close", f"session={sid}")
    sess2, records = await db.attendance_recap_session(conn, sid)
    recap_dm = _format_presensi_block(
        sess2, records, closed=True, show_record_times=True
    )
    recap_dm = f"📩 <b>Rekap presensi (DM)</b>\n\n{recap_dm}"
    await _send_presensi_dm(context, opened_by, recap_dm[:4000])
    # Admin/owner juga dapat rekap saat sesi ditutup.
    for mid in await db.list_moderator_telegram_ids(conn):
        if mid == opened_by:
            continue
        await _send_presensi_dm(context, mid, recap_dm[:4000])
        
    c_lab = _class_label(sess["class_id"])
    for r in records:
        t_uid = r["telegram_id"]
        status = dict(r).get("status", "hadir")
        amt = 25 if status == "hadir" else 10
        status_label = "Hadir" if status == "hadir" else "Izin"
        notif = f"Sesi presensi <b>{c_lab}</b> telah ditutup.\nKamu mendapatkan <b>{amt} Agra</b> (Status: {status_label})."
        await _send_presensi_dm(context, t_uid, notif)

    await refresh_presensi_announcement(context, db, conn, sid)
    await update.message.reply_text(f"Sesi <code>{sid}</code> ditutup.")


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
        db, conn, sess["id"], uid, row["role"], user_classes, status="hadir"
    )
    await update.message.reply_text(msg)
    if ok:
        await refresh_presensi_announcement(context, db, conn, sess["id"])
        await _send_presensi_dm(context, uid, msg)


async def _record_hadir(
    db, conn, session_id: int, uid: int, role: str, user_classes: list[str], status: str = "hadir"
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
    changed, old_status = await db.record_attendance(conn, session_id, uid, status)
    status_label = "Hadir" if status == "hadir" else "Izin"
    
    if changed:
        diff = 0
        if status == "hadir":
            diff = 25 if not old_status else (25 - 10)
        elif status == "izin":
            diff = 10 if not old_status else (10 - 25)
            
        if diff != 0:
            c_lab = _class_label(sess["class_id"])
            desc = f"Presensi otomatis {status_label} kelas {c_lab}"
            await db.add_agra(
                conn,
                target_id=uid,
                actor_id=uid,
                amount=diff,
                description=desc,
                chat_id=None,
                message_id=None
            )

        if old_status:
            return True, f"✅ Status diubah dari {old_status.title()} menjadi {status_label} untuk kelas {_class_label(sess['class_id'])}.", True
        return True, f"✅ Presensi kelas {_class_label(sess['class_id'])} tercatat sebagai {status_label}. Terima kasih.", True
    return True, f"Status kamu tetap {status_label} di sesi ini. Kelas: {_class_label(sess['class_id'])}.", False


async def cmd_sesi_aktif(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row:
        return
    profile = profile_from_row(row)
    if not _can_act_on_presensi(row, profile) and not can_report(row["role"], profile):
        await update.message.reply_text(
            "Hanya admin/owner/dosen/coach, atau dekan (dengan fakultas lingkup)."
        )
        return
    allowed = presence_allowed_class_ids(row["role"], profile)
    if allowed is not None and not allowed:
        await update.message.reply_text(
            "Isi <b>Kelas yang diampu</b> dan/atau <b>Fakultas</b> di /lengkapi untuk melihat sesi relevan.",
        )
        return

    open_sess = await db.recent_open_sessions(conn, 20)
    if allowed is not None:
        open_sess = [s for s in open_sess if s["class_id"] in allowed]
    if not open_sess:
        await update.message.reply_text("Tidak ada sesi presensi aktif.")
        return
    lines = ["<b>Sesi presensi aktif</b>"]
    for s in open_sess:
        lines.append(
            f"• <code>#{s['id']}</code> {_class_label(s['class_id'])} — buka {format_local_time(s['opened_at'])}"
        )
    lines.append("\nTutup dengan <code>/presensi tutup &lt;id&gt;</code>")
    await update.message.reply_text("\n".join(lines))


async def cmd_rekap_hadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row:
        return
    profile = profile_from_row(row)
    if not context.args:
        await update.message.reply_text(
            "Pakai: <code>/presensi rekap &lt;id_sesi&gt;</code> atau <code>/presensi rekap all</code> atau <code>/presensi rekap total</code>",
        )
        return

    arg = context.args[0]
    allowed_class_ids = presence_allowed_class_ids(row["role"], profile)
    if allowed_class_ids is not None and not allowed_class_ids:
        await update.message.reply_text(
            "Belum ada lingkup kelas di profil untuk rekap (dosen: kelas diampu; dekan: fakultas lingkup di /lengkapi).",
        )
        return

    if arg in ("all", "total"):
        # Lecturer hanya boleh lihat matkul yang dia ampu.
        if arg == "all":
            if allowed_class_ids is None:
                cur = await conn.execute(
                    """
                    SELECT
                        s.id,
                        s.class_id,
                        s.opened_at,
                        s.closed_at,
                        s.opened_by,
                        u.profile_json AS opener_profile_json,
                        u.first_name AS opener_first_name
                    FROM attendance_sessions s
                    LEFT JOIN users u ON u.telegram_id = s.opened_by
                    ORDER BY s.id DESC
                    """
                )
                sessions = await cur.fetchall()
            else:
                placeholders = ",".join("?" * len(allowed_class_ids))
                cur = await conn.execute(
                    f"""
                    SELECT
                        s.id,
                        s.class_id,
                        s.opened_at,
                        s.closed_at,
                        s.opened_by,
                        u.profile_json AS opener_profile_json,
                        u.first_name AS opener_first_name
                    FROM attendance_sessions s
                    LEFT JOIN users u ON u.telegram_id = s.opened_by
                    WHERE s.class_id IN ({placeholders})
                    ORDER BY s.id DESC
                    """,
                    allowed_class_ids,
                )
                sessions = await cur.fetchall()

            if not sessions:
                await update.message.reply_text("Belum ada sesi presensi.")
                return

            lines = ["<b>Rekap presensi (semua sesi)</b>"]
            for s in sessions:
                closed_at = s["closed_at"]
                opener_name = None
                if s["opener_profile_json"]:
                    try:
                        opener_json = json.loads(s["opener_profile_json"] or "{}")
                        opener_name = opener_json.get("full_name")
                    except Exception:
                        opener_name = None
                if not opener_name:
                    opener_name = s["opener_first_name"] or str(s["opened_by"])
                lines.append(
                    f"• <code>{format_local_date(s['opened_at'])} #{s['id']} </code>{_class_label(s['class_id'])} | "
                    f"_{opener_name}_"
                )
            await update.message.reply_text("\n".join(lines)[:4000])
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

        lines = ["<b>Rekap presensi per matkul</b>"]
        for r in rows:
            lines.append(f"• {int(r['session_count'])} sesi — {_class_label(r['class_id'])}")
        await update.message.reply_text("\n".join(lines)[:4000])
        return

    if not arg.isdigit():
        await update.message.reply_text(
            "Pakai: <code>/rekap_hadir <id_sesi></code> atau <code>/rekap_hadir all</code> atau <code>/rekap_hadir total</code>",
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
    hadir_records = [r for r in records if dict(r).get("status", "hadir") == "hadir"]
    izin_records = [r for r in records if dict(r).get("status", "hadir") == "izin"]

    lines = [
        f"<b>Rekap presensi</b> sesi <code>{sid}</code>",
        f"Kelas: {_class_label(sess['class_id'])}",
        f"Dibuka: {format_local_time(sess['opened_at'])}",
        f"Ditutup: {format_local_time(sess['closed_at']) if sess['closed_at'] else '— (aktif)'}",
        "",
        f"<b>Hadir ({len(hadir_records)} orang)</b>",
    ]
    for r in hadir_records:
        pj = profile_from_row(r)
        name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
        lines.append(
            f"• {name} — <code>{format_time_only(r['recorded_at'])}</code>"
        )
        
    lines.append("")
    lines.append(f"<b>Izin ({len(izin_records)} orang)</b>")
    for r in izin_records:
        pj = profile_from_row(r)
        name = pj.get("full_name") or r["first_name"] or str(r["telegram_id"])
        lines.append(
            f"• {name} — <code>{format_time_only(r['recorded_at'])}</code>"
        )
    await update.message.reply_text("\n".join(lines)[:4000])


async def cb_open_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user or not q.message:
        return
    await q.answer("Membuka sesi…")
    class_id = q.data.split(":", 1)[1]
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, q.from_user.id)
    profile = profile_from_row(row) if row else {}
    if not row or not _can_act_on_presensi(row, profile):
        await q.edit_message_text("Tidak diizinkan.")
        return
    allowed = presence_allowed_class_ids(row["role"], profile)
    if allowed is not None and class_id not in allowed:
        await q.edit_message_text("Kelas ini di luar lingkup presensi kamu.")
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
                ),
                InlineKeyboardButton(
                    "⏸️ Izin", callback_data=f"i:{sid}"[:32]
                )
            ]
        ]
    )
    await q.edit_message_text(
        text[:4000],
        reply_markup=kb,
    )
    await db.set_attendance_announce_message(
        conn, sid, q.message.message_id
    )


async def cb_attendance_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    action = q.data[0]
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
    status = "hadir" if action == "h" else "izin"
    ok, msg, _ = await _record_hadir(
        db, conn, sid, uid, row["role"], user_classes, status=status
    )
    if ok:
        await q.answer()
        await refresh_presensi_announcement(context, db, conn, sid)
        await _send_presensi_dm(context, uid, msg)
    else:
        await q.answer(msg, show_alert=True)


async def cmd_presensi_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    role = row["role"] if row else ROLE_STUDENT
    prof = profile_from_row(row) if row else {}
    
    if not context.args:
        allowed_classes = presence_allowed_class_ids(role, prof)
        can_open_presensi = allowed_classes is None or len(allowed_classes) > 0
        
        lines = ["<b>Sistem Presensi</b>"]
        
        if can_report(role, prof) or can_open_presensi:
            if can_open_presensi:
                lines.append("<code>/presensi buka</code> — Buka sesi kelas")
                lines.append("<code>/presensi tutup [id_sesi]</code> — Tutup sesi")
            
            lines.append("<code>/presensi sesi</code> — Sesi aktif" + (" <i>(terfilter)</i>" if allowed_classes is not None else ""))
            lines.append("<code>/presensi rekap</code> — Rekap kehadiran")
            
            if "d_dosen" in prof.get("position_detail", []):
                lines.append("\n<i>Catatan Dosen: pastikan mengisi Kelas yang diampu di /lengkapi.</i>")
            elif "d_dekan" in prof.get("position_detail", []):
                lines.append("\n<i>Catatan Dekan: data presensi otomatis terfilter ke fakultas lingkup.</i>")
        else:
            lines.append("<code>/presensi hadir</code> — Presensi ke sesi aktif")
            lines.append("<code>/presensi sesi</code> — Lihat daftar sesi aktif")
        
        await update.message.reply_text("\n".join(lines))
        return
        
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "buka": await cmd_buka_presensi(update, context)
        elif subcmd == "tutup": await cmd_tutup_presensi(update, context)
        elif subcmd == "sesi": await cmd_sesi_aktif(update, context)
        elif subcmd == "rekap": await cmd_rekap_hadir(update, context)
        elif subcmd == "hadir": await cmd_hadir(update, context)
        else: await update.message.reply_text("Sub-command Presensi tidak ditemukan. Ketik /presensi untuk panduan.")
    finally:
        context.args = original_args
