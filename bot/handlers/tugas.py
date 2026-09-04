"""Handler untuk fitur /tugas — Manajemen Tugas Dosen-Mahasiswa."""

from __future__ import annotations

import json
import html
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import (
    ROLE_ADMIN,
    ROLE_BEM,
    ROLE_OWNER,
    ROLE_STUDENT,
)
from bot.settings import (
    AGRA_REWARD_TUGAS,
    AGRA_REWARD_TUGAS_MABA,
    CHOICES,
    TASK_CH_ID,
)
from bot.timefmt import format_local_time

from .common import (
    is_lecturer_profile,
    lecturer_class_ids,
    normalize_multi_choice_value,
    profile_from_row,
    user_row,
    get_user_jabatans,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _class_label(class_id: str) -> str:
    for item in CHOICES.get("classes", []) + CHOICES.get("clubs", []):
        if item.get("id") == class_id:
            return str(item.get("label", class_id))
    return class_id


def _can_manage_tasks(role: str, profile: dict) -> bool:
    """Dosen, Guru Besar, Coach, Admin, Owner, Panitia Ospek bisa membuka tugas."""
    if role in (ROLE_OWNER, ROLE_ADMIN):
        return True
    jabs = get_user_jabatans(profile)
    return "d_dosen" in jabs or "d_guru_besar" in jabs or "d_coach" in jabs or "p_panitia_ospek" in jabs


def _task_class_ids_for_lecturer(profile: dict) -> list[str]:
    """Matkul yang bisa diberi tugas oleh dosen/coach/guru besar."""
    return lecturer_class_ids(profile)


def _student_enrolled_class_ids(profile: dict) -> list[str]:
    """Semua kelas yang diikuti mahasiswa (otomatis dari jurusan + manual)."""
    major = profile.get("major")
    auto = []
    for item in CHOICES.get("classes", []):
        cid = item.get("id")
        m = item.get("majors")
        if not m or m == major:
            auto.append(str(cid))
    enrolled = normalize_multi_choice_value(profile.get("class_enrolled"))
    club = normalize_multi_choice_value(profile.get("club_enrolled"))
    return list(dict.fromkeys(auto + enrolled + club))


def _submission_status_emoji(status: str) -> str:
    return {
        "submitted": "⏳",
        "accepted": "✅",
        "rejected": "❌",
    }.get(status, "⬜")


def _submission_status_label(status: str) -> str:
    return {
        "submitted": "Menunggu Review",
        "accepted": "Diterima",
        "rejected": "Ditolak",
    }.get(status, "Belum Dikerjakan")


def _task_hashtags(class_id: str, title: str) -> str:
    title_tag = title.replace(" ", "_").replace("-", "_")
    # remove non-alphanumeric except underscore
    title_tag = "".join(c for c in title_tag if c.isalnum() or c == "_")
    return f"#{class_id} #{title_tag}"


async def _send_dm(context: ContextTypes.DEFAULT_TYPE, uid: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=uid, text=text)
    except Exception as e:
        log.warning("DM tugas ke %s: %s", uid, e)


async def _post_or_update_channel(
    context: ContextTypes.DEFAULT_TYPE,
    db,
    conn,
    submission_id: int,
) -> None:
    """Post or edit submission message in TASK_CH_ID channel."""
    if not TASK_CH_ID:
        return
    sub = await db.get_submission(conn, submission_id)
    if not sub:
        return
    task = await db.get_task(conn, sub["task_id"])
    if not task:
        return

    # Get student info
    student_row = await db.get_user(conn, sub["student_id"])
    student_prof = json.loads(student_row["profile_json"] or "{}") if student_row else {}
    student_name = (
        student_prof.get("full_name")
        or (f"{student_row['first_name'] or ''}" if student_row else "")
        or str(sub["student_id"])
    )

    hashtags = _task_hashtags(task["class_id"], task["title"])
    status_emoji = _submission_status_emoji(sub["status"])
    status_label = _submission_status_label(sub["status"])

    content_preview = sub["content"]
    if len(content_preview) > 500:
        content_preview = content_preview[:500] + "…"
    content_preview = html.escape(content_preview)
    student_name_esc = html.escape(student_name)
    task_title_esc = html.escape(task['title'])

    text = (
        f"📋 {hashtags}\n\n"
        f"👤 <b>Pengirim:</b> {student_name_esc}\n"
        f"📚 <b>Matkul:</b> {_class_label(task['class_id'])}\n"
        f"📝 <b>Tugas:</b> {task_title_esc}\n\n"
        f"<b>Hasil:</b>\n{content_preview}\n\n"
        f"<b>Status:</b> {status_emoji} {status_label}"
    )
    if sub["status"] == "rejected" and sub["reject_reason"]:
        text += f"\n<b>Alasan:</b> {sub['reject_reason']}"

    existing_msg_id = sub["channel_message_id"]
    if existing_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=TASK_CH_ID,
                message_id=existing_msg_id,
                text=text[:4000],
            )
            return
        except Exception as e:
            log.debug("edit channel task msg: %s", e)

    # Post new
    try:
        msg = await context.bot.send_message(
            chat_id=TASK_CH_ID,
            text=text[:4000],
        )
        await db.set_submission_channel_message(conn, submission_id, msg.message_id)
    except Exception as e:
        log.warning("post channel task: %s", e)


# ── Command Router ──────────────────────────────────────────────

async def cmd_tugas_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return

    role = row["role"]
    prof = profile_from_row(row)

    if not context.args:
        # Show role-appropriate menu
        is_lecturer = _can_manage_tasks(role, prof)
        is_student = role in (ROLE_STUDENT, ROLE_BEM)

        if is_lecturer:
            await _show_lecturer_dashboard(update, context, db, conn, row, prof)
        elif is_student:
            await _show_student_dashboard(update, context, db, conn, row, prof)
        else:
            await update.message.reply_text("Fitur /tugas hanya untuk dosen/guru besar/coach dan mahasiswa.")
        return

    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "buka":
            await cmd_buka_tugas(update, context)
        elif subcmd == "tutup":
            await cmd_tutup_tugas(update, context)
        elif subcmd == "lihat":
            # same as no-arg dashboard
            is_lecturer = _can_manage_tasks(role, prof)
            is_student = role in (ROLE_STUDENT, ROLE_BEM)
            if is_lecturer:
                await _show_lecturer_dashboard(update, context, db, conn, row, prof)
            elif is_student:
                await _show_student_dashboard(update, context, db, conn, row, prof)
            else:
                await update.message.reply_text("Fitur /tugas hanya untuk dosen/guru besar/coach dan mahasiswa.")
        else:
            await update.message.reply_text(
                "Sub-command tidak ditemukan. Ketik /tugas untuk panduan."
            )
    finally:
        context.args = original_args


# ── Lecturer Dashboard ──────────────────────────────────────────

async def _show_lecturer_dashboard(update, context, db, conn, row, prof):
    uid = update.effective_user.id
    tasks = await db.list_tasks_by_lecturer(conn, uid, only_open=False)

    lines = ["📋 <b>Dashboard Tugas (Pengajar)</b>\n"]

    if not tasks:
        lines.append("<i>Belum ada tugas yang dibuat.</i>")
    else:
        for t in tasks[:15]:
            status = "🟢 Aktif" if t["is_open"] else "🔴 Ditutup"
            # Count submissions
            subs = await db.list_submissions_for_task(conn, t["id"])
            accepted = sum(1 for s in subs if s["status"] == "accepted")
            pending = sum(1 for s in subs if s["status"] == "submitted")
            lines.append(
                f"• <code>#{t['id']}</code> {_class_label(t['class_id'])} — <b>{t['title']}</b>\n"
                f"  {status} | 📨 {len(subs)} submit ({accepted} ACC, {pending} pending)"
            )

    lines.append("\n<b>Perintah:</b>")
    lines.append("<code>/tugas buka</code> — Buka tugas baru")
    lines.append("<code>/tugas tutup [id]</code> — Tutup tugas")

    kb_rows = []
    open_tasks = [t for t in tasks if t["is_open"]]
    if open_tasks:
        for t in open_tasks[:8]:
            kb_rows.append([
                InlineKeyboardButton(
                    f"📋 #{t['id']} {t['title'][:25]}",
                    callback_data=f"tdv:{t['id']}"[:64],
                )
            ])
    kb_rows.append([InlineKeyboardButton("➕ Buka Tugas Baru", callback_data="tgbuka")])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
    )


# ── Student Dashboard ───────────────────────────────────────────

async def _show_student_dashboard(update, context, db, conn, row, prof):
    uid = update.effective_user.id
    class_ids = _student_enrolled_class_ids(prof)
    tasks = await db.list_tasks_for_classes(conn, class_ids, only_open=True)

    lines = ["📋 <b>Dashboard Tugas (Mahasiswa)</b>\n"]

    if not tasks:
        lines.append("<i>Tidak ada tugas aktif saat ini.</i>")
        await update.message.reply_text("\n".join(lines))
        return

    kb_rows = []
    for t in tasks[:15]:
        sub = await db.get_submission_by_task_student(conn, t["id"], uid)
        if sub:
            status = sub["status"]
            emoji = _submission_status_emoji(status)
            label = _submission_status_label(status)
        else:
            emoji = "⬜"
            label = "Belum Dikerjakan"

        lines.append(
            f"• <code>#{t['id']}</code> {_class_label(t['class_id'])} — <b>{t['title']}</b>\n"
            f"  Status: {emoji} {label}"
        )

        # Show action button for tasks that can be submitted
        can_submit = (not sub) or (sub and sub["status"] in ("rejected", "submitted"))
        if can_submit:
            btn_label = "📝 Kerjakan" if not sub else ("📝 Kirim Ulang" if sub["status"] == "rejected" else "✏️ Ubah")
            kb_rows.append([
                InlineKeyboardButton(
                    f"{btn_label}: {t['title'][:20]}",
                    callback_data=f"tsi:{t['id']}"[:64],
                )
            ])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
    )


# ── Buka Tugas ──────────────────────────────────────────────────

async def cmd_buka_tugas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    prof = profile_from_row(row) if row else {}
    if not row or not _can_manage_tasks(row["role"], prof):
        await update.message.reply_text("Hanya dosen/guru besar/coach/admin/owner yang bisa membuka tugas.")
        return

    class_ids = _task_class_ids_for_lecturer(prof)
    if row["role"] in (ROLE_OWNER, ROLE_ADMIN) and not class_ids:
        # Admin/owner can open for any class
        class_ids = [str(item.get("id")) for item in CHOICES.get("classes", []) + CHOICES.get("clubs", [])]

    if not class_ids:
        await update.message.reply_text(
            "Isi <b>Kelas yang diampu</b> di /lengkapi agar ada matkul untuk tugas."
        )
        return

    rows = []
    for cid in class_ids:
        lab = _class_label(cid)
        rows.append([InlineKeyboardButton(lab, callback_data=f"tb:{cid}"[:64])])
    rows.append([InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")])

    await update.message.reply_text(
        "Pilih matkul untuk tugas baru:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ── Tutup Tugas ─────────────────────────────────────────────────

async def cmd_tutup_tugas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    prof = profile_from_row(row) if row else {}

    if not row or not _can_manage_tasks(row["role"], prof):
        await update.message.reply_text("Tidak diizinkan.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Pakai: <code>/tugas tutup &lt;id_tugas&gt;</code>")
        return

    task_id = int(context.args[0])
    task = await db.get_task(conn, task_id)
    if not task:
        await update.message.reply_text("Tugas tidak ditemukan.")
        return
    if not task["is_open"]:
        await update.message.reply_text(f"Tugas <code>#{task_id}</code> sudah ditutup.")
        return

    # Only creator or admin/owner can close
    if task["created_by"] != uid and row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Hanya pembuat tugas atau admin/owner yang bisa menutup tugas ini.")
        return

    await db.close_task(conn, task_id)
    await db.add_audit(conn, uid, "task_close", f"task={task_id}")
    await update.message.reply_text(
        f"✅ Tugas <code>#{task_id}</code> — <b>{task['title']}</b> telah ditutup."
    )

    # Notify students
    class_ids = [task["class_id"]]
    student_ids = await db.user_ids_matching_profile_filter(conn, class_id=task["class_id"])
    for sid in student_ids:
        await _send_dm(
            context, sid,
            f"📢 Tugas <b>{task['title']}</b> ({_class_label(task['class_id'])}) telah ditutup."
        )


# ── Callback Handlers ───────────────────────────────────────────

async def cb_tugas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Central callback handler for all tugas callbacks."""
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    data = q.data
    conn = _conn(context)
    db = _db(context)
    uid = q.from_user.id

    # ── tb:<class_id> — Lecturer picks class to create task
    if data.startswith("tb:"):
        await q.answer()
        class_id = data.split(":", 1)[1]
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        await db.set_onboarding_step(conn, uid, f"TUGAS_JUDUL:{class_id}")
        await q.edit_message_text(
            f"📝 Buka tugas baru untuk <b>{_class_label(class_id)}</b>.\n\n"
            "Ketik judul tugas:"
        )
        return

    # ── tgbuka — Shortcut button to open task creation flow
    if data == "tgbuka":
        await q.answer()
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        class_ids = _task_class_ids_for_lecturer(prof)
        if row["role"] in (ROLE_OWNER, ROLE_ADMIN) and not class_ids:
            class_ids = [str(item.get("id")) for item in CHOICES.get("classes", []) + CHOICES.get("clubs", [])]

        if not class_ids:
            await q.edit_message_text("Isi <b>Kelas yang diampu</b> di /lengkapi.")
            return

        rows = []
        for cid in class_ids:
            lab = _class_label(cid)
            rows.append([InlineKeyboardButton(lab, callback_data=f"tb:{cid}"[:64])])
        rows.append([InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")])

        await q.edit_message_text(
            "Pilih matkul untuk tugas baru:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    # ── tsi:<task_id> — Student starts submission
    if data.startswith("tsi:"):
        await q.answer()
        task_id = int(data.split(":", 1)[1])
        row = await user_row(conn, db, uid)
        if not row or row["role"] not in (ROLE_STUDENT, ROLE_BEM):
            await q.edit_message_text("Hanya mahasiswa yang bisa mengerjakan tugas.")
            return

        task = await db.get_task(conn, task_id)
        if not task or not task["is_open"]:
            await q.edit_message_text("Tugas tidak ditemukan atau sudah ditutup.")
            return

        # Check if already accepted
        sub = await db.get_submission_by_task_student(conn, task_id, uid)
        if sub and sub["status"] == "accepted":
            await q.edit_message_text("Tugas ini sudah diterima, tidak bisa diubah lagi.")
            return

        await db.set_onboarding_step(conn, uid, f"TUGAS_INPUT:{task_id}")
        prompt = f"📝 <b>{task['title']}</b> — {_class_label(task['class_id'])}\n\nKetik jawaban/hasil tugas kamu:"
        if sub and sub["status"] == "rejected":
            prompt += f"\n\n⚠️ Submission sebelumnya ditolak.\n<b>Alasan:</b> {sub['reject_reason'] or '-'}"
        elif sub and sub["status"] == "submitted":
            prompt += f"\n\n📌 Kamu sudah pernah mengirim. Kirim ulang untuk mengubah jawaban."

        await q.edit_message_text(prompt)
        return

    # ── tdv:<task_id> — Lecturer views task detail + submissions
    if data.startswith("tdv:"):
        await q.answer()
        task_id = int(data.split(":", 1)[1])
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        task = await db.get_task(conn, task_id)
        if not task:
            await q.edit_message_text("Tugas tidak ditemukan.")
            return

        subs = await db.list_submissions_for_task(conn, task_id)
        status_text = "🟢 Aktif" if task["is_open"] else "🔴 Ditutup"

        lines = [
            f"📋 <b>Detail Tugas</b> <code>#{task_id}</code>",
            f"<b>Matkul:</b> {_class_label(task['class_id'])}",
            f"<b>Judul:</b> {task['title']}",
            f"<b>Status:</b> {status_text}",
            f"<b>Dibuka:</b> {format_local_time(task['created_at'])}",
            f"\n<b>Submissions ({len(subs)}):</b>",
        ]

        kb_rows = []
        if not subs:
            lines.append("<i>Belum ada submission.</i>")
        else:
            for s in subs[:20]:
                sp = json.loads(s["profile_json"] or "{}")
                sname = sp.get("full_name") or s["first_name"] or str(s["student_id"])
                emoji = _submission_status_emoji(s["status"])
                lines.append(f"• {emoji} {sname} — {_submission_status_label(s['status'])}")

                if s["status"] == "submitted":
                    kb_rows.append([
                        InlineKeyboardButton(
                            f"👁️ {sname[:15]}",
                            callback_data=f"tsv:{s['id']}"[:64],
                        )
                    ])

        kb_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cancel_action")])

        await q.edit_message_text(
            "\n".join(lines)[:4000],
            reply_markup=InlineKeyboardMarkup(kb_rows),
        )
        return

    # ── tsv:<sub_id> — Lecturer views a specific submission
    if data.startswith("tsv:"):
        await q.answer()
        sub_id = int(data.split(":", 1)[1])
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        sub = await db.get_submission(conn, sub_id)
        if not sub:
            await q.edit_message_text("Submission tidak ditemukan.")
            return

        task = await db.get_task(conn, sub["task_id"])
        student_row = await db.get_user(conn, sub["student_id"])
        sp = json.loads(student_row["profile_json"] or "{}") if student_row else {}
        sname = sp.get("full_name") or (student_row["first_name"] if student_row else "") or str(sub["student_id"])

        content = sub["content"]
        if len(content) > 2000:
            content = content[:2000] + "…"
        content = html.escape(content)
        sname_esc = html.escape(sname)
        task_title_esc = html.escape(task['title'] if task else '?')

        lines = [
            f"📋 <b>Submission</b> <code>#{sub_id}</code>",
            f"<b>Tugas:</b> {task_title_esc} ({_class_label(task['class_id']) if task else '?'})",
            f"<b>Pengirim:</b> {sname_esc}",
            f"<b>Waktu:</b> {format_local_time(sub['submitted_at'])}",
            f"<b>Status:</b> {_submission_status_emoji(sub['status'])} {_submission_status_label(sub['status'])}",
            f"\n<b>Jawaban:</b>\n{content}",
        ]

        kb = []
        if sub["status"] == "submitted":
            kb.append([
                InlineKeyboardButton("✅ ACC", callback_data=f"tacc:{sub_id}"[:64]),
                InlineKeyboardButton("❌ Tolak", callback_data=f"trej:{sub_id}"[:64]),
            ])
        kb.append([
            InlineKeyboardButton("⬅️ Kembali ke tugas", callback_data=f"tdv:{sub['task_id']}"[:64]),
        ])

        await q.edit_message_text(
            "\n".join(lines)[:4000],
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    # ── tacc:<sub_id> — Lecturer accepts submission
    if data.startswith("tacc:"):
        await q.answer("Menerima tugas…")
        sub_id = int(data.split(":", 1)[1])
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        sub = await db.get_submission(conn, sub_id)
        if not sub:
            await q.edit_message_text("Submission tidak ditemukan.")
            return

        ok = await db.review_submission(conn, sub_id, accept=True, reviewed_by=uid)
        if not ok:
            await q.edit_message_text("Submission sudah di-review sebelumnya.")
            return

        task = await db.get_task(conn, sub["task_id"])
        task_title = task["title"] if task else "?"
        class_label = _class_label(task["class_id"]) if task else "?"
        
        reward = AGRA_REWARD_TUGAS_MABA if task and task["class_id"] == "ospek_maba" else AGRA_REWARD_TUGAS

        # Add Agra reward
        await db.add_agra(
            conn,
            target_id=sub["student_id"],
            actor_id=uid,
            amount=reward,
            description=f"Tugas diterima: {task_title} ({class_label})",
            chat_id=None,
            message_id=None,
        )

        await db.add_audit(conn, uid, "task_accept", f"sub={sub_id} task={sub['task_id']}")

        # Update channel
        await _post_or_update_channel(context, db, conn, sub_id)

        # Notify student
        await _send_dm(
            context, sub["student_id"],
            f"✅ Tugas <b>{task_title}</b> ({class_label}) telah <b>diterima</b>!\n"
            f"🎁 Kamu mendapat <b>{reward} Agra</b>."
        )

        # Get student name for feedback
        student_row = await db.get_user(conn, sub["student_id"])
        sp = json.loads(student_row["profile_json"] or "{}") if student_row else {}
        sname = sp.get("full_name") or (student_row["first_name"] if student_row else "") or str(sub["student_id"])

        await q.edit_message_text(
            f"✅ Submission dari <b>{sname}</b> untuk tugas <b>{task_title}</b> telah diterima.\n"
            f"Agra +{reward} diberikan."
        )
        return

    # ── trej:<sub_id> — Lecturer starts rejection (needs reason)
    if data.startswith("trej:"):
        await q.answer()
        sub_id = int(data.split(":", 1)[1])
        row = await user_row(conn, db, uid)
        prof = profile_from_row(row) if row else {}
        if not row or not _can_manage_tasks(row["role"], prof):
            await q.edit_message_text("Tidak diizinkan.")
            return

        sub = await db.get_submission(conn, sub_id)
        if not sub or sub["status"] != "submitted":
            await q.edit_message_text("Submission tidak valid atau sudah di-review.")
            return

        await db.set_onboarding_step(conn, uid, f"TUGAS_TOLAK:{sub_id}")
        await q.edit_message_text(
            f"❌ Ketik alasan penolakan untuk submission <code>#{sub_id}</code>:"
        )
        return


# ── Onboarding Step Handlers (called from messages.py) ──────────

async def handle_tugas_judul(
    update: Update, context: ContextTypes.DEFAULT_TYPE, class_id: str
) -> None:
    """Handle text input for task title creation."""
    if not update.effective_user or not update.message or not update.message.text:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    title = update.message.text.strip()

    if not title or len(title) > 200:
        await update.message.reply_text("Judul tugas tidak valid (maks 200 karakter). Coba lagi:")
        return

    row = await user_row(conn, db, uid)
    prof = profile_from_row(row) if row else {}
    if not row or not _can_manage_tasks(row["role"], prof):
        await db.set_onboarding_step(conn, uid, None)
        await update.message.reply_text("Tidak diizinkan.")
        return

    task_id = await db.create_task(conn, class_id=class_id, title=title, created_by=uid)
    await db.set_onboarding_step(conn, uid, None)
    await db.add_audit(conn, uid, "task_create", f"task={task_id} class={class_id}")

    class_label = _class_label(class_id)
    await update.message.reply_text(
        f"✅ Tugas baru dibuat!\n\n"
        f"<b>ID:</b> <code>#{task_id}</code>\n"
        f"<b>Matkul:</b> {class_label}\n"
        f"<b>Judul:</b> {title}\n\n"
        f"Tugas akan otomatis ditutup dalam 7 hari.\n"
        f"Tutup manual: <code>/tugas tutup {task_id}</code>"
    )

    # Notify enrolled students
    student_ids = await db.user_ids_matching_profile_filter(conn, class_id=class_id)
    # Get lecturer name
    lecturer_name = prof.get("full_name") or (row["first_name"] if row else "") or str(uid)

    for sid in student_ids:
        if sid == uid:
            continue
        await _send_dm(
            context, sid,
            f"📢 <b>Tugas Baru!</b>\n\n"
            f"📚 <b>Matkul:</b> {class_label}\n"
            f"📝 <b>Judul:</b> {title}\n"
            f"👤 <b>Dari:</b> {lecturer_name}\n\n"
            f"Ketik /tugas untuk melihat dan mengerjakan."
        )


async def handle_tugas_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int
) -> None:
    """Handle text input for student submission."""
    if not update.effective_user or not update.message or not update.message.text:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    content = update.message.text.strip()

    if not content:
        await update.message.reply_text("Jawaban tidak boleh kosong. Coba lagi:")
        return

    task = await db.get_task(conn, task_id)
    if not task or not task["is_open"]:
        await db.set_onboarding_step(conn, uid, None)
        await update.message.reply_text("Tugas tidak ditemukan atau sudah ditutup.")
        return

    sub_id = await db.submit_task(conn, task_id=task_id, student_id=uid, content=content)
    await db.set_onboarding_step(conn, uid, None)

    if sub_id == -1:
        await update.message.reply_text("Tugas ini sudah diterima, tidak bisa diubah lagi.")
        return

    await db.add_audit(conn, uid, "task_submit", f"sub={sub_id} task={task_id}")

    class_label = _class_label(task["class_id"])
    await update.message.reply_text(
        f"✅ Jawaban terkirim!\n\n"
        f"📚 <b>Matkul:</b> {class_label}\n"
        f"📝 <b>Tugas:</b> {task['title']}\n\n"
        f"Menunggu review dari dosen/coach. Kamu akan mendapat notifikasi."
    )

    # Post to channel
    await _post_or_update_channel(context, db, conn, sub_id)

    # Notify lecturer
    student_row = await db.get_user(conn, uid)
    sp = json.loads(student_row["profile_json"] or "{}") if student_row else {}
    sname = sp.get("full_name") or (student_row["first_name"] if student_row else "") or str(uid)

    await _send_dm(
        context, task["created_by"],
        f"📨 <b>Submission Masuk!</b>\n\n"
        f"👤 <b>Dari:</b> {sname}\n"
        f"📚 <b>Matkul:</b> {class_label}\n"
        f"📝 <b>Tugas:</b> {task['title']}\n\n"
        f"Ketik /tugas untuk melihat dan mereview."
    )


async def handle_tugas_tolak(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sub_id: int
) -> None:
    """Handle text input for rejection reason."""
    if not update.effective_user or not update.message or not update.message.text:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    reason = update.message.text.strip()

    if not reason:
        await update.message.reply_text("Alasan tidak boleh kosong. Coba lagi:")
        return

    sub = await db.get_submission(conn, sub_id)
    if not sub or sub["status"] != "submitted":
        await db.set_onboarding_step(conn, uid, None)
        await update.message.reply_text("Submission tidak valid atau sudah di-review.")
        return

    ok = await db.review_submission(conn, sub_id, accept=False, reviewed_by=uid, reason=reason)
    await db.set_onboarding_step(conn, uid, None)

    if not ok:
        await update.message.reply_text("Gagal menolak submission.")
        return

    await db.add_audit(conn, uid, "task_reject", f"sub={sub_id}")

    task = await db.get_task(conn, sub["task_id"])
    task_title = task["title"] if task else "?"
    class_label = _class_label(task["class_id"]) if task else "?"

    # Update channel
    await _post_or_update_channel(context, db, conn, sub_id)

    # Notify student
    await _send_dm(
        context, sub["student_id"],
        f"❌ Tugas <b>{task_title}</b> ({class_label}) <b>ditolak</b>.\n"
        f"<b>Alasan:</b> {reason}\n\n"
        f"Silakan kirim ulang melalui /tugas."
    )

    # Get student name for feedback
    student_row = await db.get_user(conn, sub["student_id"])
    sp = json.loads(student_row["profile_json"] or "{}") if student_row else {}
    sname = sp.get("full_name") or (student_row["first_name"] if student_row else "") or str(sub["student_id"])

    await update.message.reply_text(
        f"❌ Submission dari <b>{sname}</b> untuk tugas <b>{task_title}</b> ditolak.\n"
        f"Alasan: {reason}\n"
        f"Mahasiswa telah dinotifikasi untuk kirim ulang."
    )
