"""Perintah /ktm, /ktm_foto — gambar KTM (hanya chat privat)."""

from __future__ import annotations

import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes, filters

from bot.database import ROLE_PUBLIC, ROLE_STUDENT
from bot.ktm_card import render_ktm_png_bytes

from .common import profile_from_row, user_row

log = logging.getLogger(__name__)

# Step onboarding: tunggu satu foto dari user.
STEP_KTM_PHOTO = "KTM_PHOTO"


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _private_only_reply(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


async def _download_telegram_photo(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes | None:
    try:
        tg_file = await context.bot.get_file(file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        log.warning("Unduh foto KTM gagal file_id=%s", file_id[:20], exc_info=True)
        return None


async def cmd_ktm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text("Perintah /ktm hanya bisa dipakai di chat privat dengan bot.")
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    if row["role"] == ROLE_PUBLIC:
        await update.message.reply_text("Selesaikan pendaftaran dulu (kode akses / role mahasiswa).")
        return
    if row["role"] != ROLE_STUDENT:
        await update.message.reply_text("KTM digital hanya untuk mahasiswa.")
        return

    profile = profile_from_row(row)
    agra = await db.agra_total(conn, uid)
    photo_bytes: bytes | None = None
    fid = (profile.get("ktm_photo_file_id") or "").strip()
    if fid:
        photo_bytes = await _download_telegram_photo(context, fid)

    try:
        png = render_ktm_png_bytes(
            telegram_id=uid,
            profile=profile,
            agra=agra,
            use_cache=True,
            photo_bytes=photo_bytes,
        )
    except FileNotFoundError as e:
        await update.message.reply_text(f"Template KTM belum siap: {e}")
        return
    except Exception:
        log.exception("render KTM gagal uid=%s", uid)
        await update.message.reply_text("Gagal membuat gambar KTM. Coba lagi nanti.")
        return

    cap = "Kartu tanda mahasiswa (digital)."
    if fid and photo_bytes is None:
        cap += " (Foto tidak bisa diunduh lagi — kirim ulang dengan /ktm_foto.)"

    await update.message.reply_photo(
        photo=BytesIO(png),
        filename="ktm.png",
        caption=cap,
    )


async def cmd_ktm_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text(
            "/ktm_foto hanya di chat privat dengan bot."
        )
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    if row["role"] == ROLE_PUBLIC:
        await update.message.reply_text("Selesaikan pendaftaran dulu.")
        return
    if row["role"] != ROLE_STUDENT:
        await update.message.reply_text("Hanya mahasiswa yang bisa mengatur foto KTM.")
        return

    await db.set_onboarding_step(conn, uid, STEP_KTM_PHOTO)
    await update.message.reply_text(
        "Kirim *satu foto* (wajah) di chat ini. Foto akan dipotong memenuhi kotak di KTM.\n\n"
        "Setelah tersimpan, ketik /ktm untuk melihat kartu.\n"
        "_Kirim foto baru lagi kapan saja dengan /ktm_foto untuk mengganti._",
        parse_mode="Markdown",
    )


async def on_ktm_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.photo:
        return
    if not _private_only_reply(update):
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    step = (row["onboarding_step"] or "").strip()
    if step != STEP_KTM_PHOTO:
        return
    if row["role"] != ROLE_STUDENT:
        await db.set_onboarding_step(conn, uid, None)
        return

    photos = update.message.photo
    largest = photos[-1]
    file_id = largest.file_id

    await db.set_profile_partial(conn, uid, {"ktm_photo_file_id": file_id})
    await db.set_onboarding_step(conn, uid, None)
    await update.message.reply_text(
        "✅ Foto KTM tersimpan. Ketik /ktm untuk melihat kartu."
    )


# Filter untuk registrasi handler (chat privat saja).
KT_PRIVATE = filters.ChatType.PRIVATE
