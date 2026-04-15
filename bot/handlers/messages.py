from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
import time
import re

from bot.database import role_can_report
from bot.settings import PROFILE_FIELDS, FORWARD_GROUP_ID

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
        is_trigger = False
        try:
            from .triggers import check_and_execute_trigger
            is_trigger = await check_and_execute_trigger(conn, update, context, text)
        except ImportError:
            pass
            
        if not is_trigger and FORWARD_GROUP_ID:
            await context.bot.send_message(
                chat_id=FORWARD_GROUP_ID,
                text=f"Pesan dari {update.effective_user.first_name} (@{update.effective_user.username}):\n\n{text}\n\n#ID_{uid}"
            )
            if row["role"] == "public":
                await update.message.reply_text("Pesan Anda telah diteruskan ke tim kami.")
        return
        
    if step == "INPUT_CODE":
        code = text.strip()
        cur = await conn.execute("SELECT * FROM access_codes WHERE code = ? AND used_by IS NULL", (code,))
        code_row = await cur.fetchone()
        if code_row:
            await conn.execute("UPDATE access_codes SET used_by = ?, used_at = ? WHERE code = ?", (uid, time.time(), code))
            await db.set_role(conn, uid, "student")
            await db.set_onboarding_step(conn, uid, None)
            await conn.commit()
            await update.message.reply_text("Kode valid! Role Anda telah diperbarui menjadi student.\nSilakan ketik /lengkapi untuk mulai melengkapi data diri.")
        else:
            await update.message.reply_text("Kode tidak valid atau sudah digunakan. Silakan coba lagi, atau ketik /start untuk membatalkan.")
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


async def track_group_activity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    conn = _conn(context)
    db = _db(context)
    u = update.effective_user
    await db.touch_group_seen_user(
        conn,
        chat_id=update.effective_chat.id,
        telegram_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name,
        is_bot=u.is_bot,
    )

async def on_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    if not FORWARD_GROUP_ID or update.effective_chat.id != FORWARD_GROUP_ID:
        return
        
    reply = update.message.reply_to_message
    if reply and reply.from_user and reply.from_user.id == context.bot.id:
        match = re.search(r"#ID_(\d+)", reply.text or "")
        if match:
            target_id = int(match.group(1))
            try:
                await context.bot.send_message(chat_id=target_id, text=update.message.text)
                await update.message.reply_text("✅ Balasan berhasil dikirim ke user.")
            except Exception as e:
                await update.message.reply_text(f"Gagal mengirim balasan: {e}")
