from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import role_can_report
from bot.settings import PROFILE_FIELDS

from .common import (
    field_label_for_key,
    missing_required_fields,
    profile_from_row,
    user_row,
)

ADMIN_PROFILE_TARGET_UD = "admin_profile_target"
LENGKAPI_DONE_KEY = "__lengkapi_done"


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _is_lengkapi_done(profile: dict) -> bool:
    return bool(profile.get(LENGKAPI_DONE_KEY))


async def _mark_lengkapi_done_if_complete(conn, db, telegram_id: int) -> None:
    row = await user_row(conn, db, telegram_id)
    if not row:
        return
    profile = profile_from_row(row)
    if _is_lengkapi_done(profile):
        return
    if not missing_required_fields(profile, row["role"]):
        await db.set_profile_partial(conn, telegram_id, {LENGKAPI_DONE_KEY: True})


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    step = row["onboarding_step"] or ""
    text = update.message.text.strip()
    if not step:
        return

    if step.startswith("ADMIN_TEXT_LC:"):
        field_key = step.split(":", 1)[1]
        target_tid = context.user_data.get(ADMIN_PROFILE_TARGET_UD)
        row_actor = await user_row(conn, db, uid)
        if not target_tid or not row_actor or not role_can_report(row_actor["role"]):
            await db.set_onboarding_step(conn, uid, None)
            return
        await db.set_profile_partial(conn, target_tid, {field_key: text})
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(
            conn,
            uid,
            "admin_profile_set",
            f"target={target_tid} key={field_key}",
        )
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        await update.message.reply_text(
            f"✅ {lab} untuk `{target_tid}` disimpan."
        )
        return

    if step.startswith("TEXT_LC:"):
        field_key = step.split(":", 1)[1]
        profile = profile_from_row(row)
        if _is_lengkapi_done(profile):
            await db.set_onboarding_step(conn, uid, None)
            await update.message.reply_text("/lengkapi sudah ditutup. Gunakan /ubah.")
            return
        await db.set_profile_partial(conn, uid, {field_key: text})
        await _mark_lengkapi_done_if_complete(conn, db, uid)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        await update.message.reply_text(f"✅ {lab} disimpan.")
        return

    if step.startswith("TEXT_EC:"):
        field_key = step.split(":", 1)[1]
        rid = await db.add_profile_request(conn, uid, {field_key: text})
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await update.message.reply_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin."
        )
        from .commands import _notify_moderators_profile

        await _notify_moderators_profile(
            context, db, conn, rid, uid, {field_key: text}
        )
        return
