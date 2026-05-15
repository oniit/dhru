"""Perintah /karpeg, /karpeg_foto — gambar Kartu Pegawai (hanya chat privat)."""

from __future__ import annotations

import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes, filters

from bot.database import ROLE_PUBLIC, ROLE_STUDENT, ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL
from bot.karpeg_card import render_karpeg_png_bytes

from .common import profile_from_row, user_row

log = logging.getLogger(__name__)

# Step onboarding: tunggu satu foto dari user.
STEP_KARPEG_PHOTO = "KARPEG_PHOTO"


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
        log.warning("Unduh foto Karpeg gagal file_id=%s", file_id[:20], exc_info=True)
        return None


async def cmd_karpeg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text("Perintah /karpeg hanya bisa dipakai di chat privat dengan bot.")
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    if row["role"] == ROLE_PUBLIC:
        await update.message.reply_text("Selesaikan pendaftaran dulu (kode akses).")
        return
    if row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Kartu Pegawai hanya untuk staf/dosen/founder.")
        return

    profile = profile_from_row(row)
    agra = await db.agra_total(conn, uid)
    photo_bytes: bytes | None = None
    fid = (profile.get("karpeg_photo_file_id") or "").strip()
    if fid:
        photo_bytes = await _download_telegram_photo(context, fid)

    try:
        png = render_karpeg_png_bytes(
            telegram_id=uid,
            profile=profile,
            agra=agra,
            role=row["role"],
            use_cache=True,
            photo_bytes=photo_bytes,
        )
    except FileNotFoundError as e:
        await update.message.reply_text(f"Template Karpeg belum siap: {e}")
        return
    except Exception:
        log.exception("render Karpeg gagal uid=%s", uid)
        await update.message.reply_text("Gagal membuat gambar Kartu Pegawai. Coba lagi nanti.")
        return

    cap = "Kartu Pegawai (digital)."
    if fid and photo_bytes is None:
        cap += " (Foto tidak bisa diunduh lagi — kirim ulang dengan /karpeg\\_foto.)"

    await update.message.reply_photo(
        photo=BytesIO(png),
        filename="karpeg.png",
        caption=cap,
    )


async def cmd_karpeg_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text(
            "/karpeg_foto hanya di chat privat dengan bot."
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
    if row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Hanya staf/dosen/founder yang bisa mengatur foto Karpeg.")
        return

    await db.set_onboarding_step(conn, uid, STEP_KARPEG_PHOTO)
    await update.message.reply_text(
        "Kirim *satu foto* (wajah) di chat ini. Foto akan dipotong memenuhi kotak di Kartu Pegawai.\n\n"
        "Setelah tersimpan, ketik /karpeg untuk melihat kartu.\n"
        "Kirim foto baru lagi kapan saja dengan `/karpeg_foto` untuk mengganti.",
        parse_mode="Markdown",
    )


async def on_karpeg_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if step != STEP_KARPEG_PHOTO:
        return
    if row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await db.set_onboarding_step(conn, uid, None)
        return

    photos = update.message.photo
    largest = photos[-1]
    file_id = largest.file_id

    await db.set_profile_partial(conn, uid, {"karpeg_photo_file_id": file_id})
    await db.set_onboarding_step(conn, uid, None)
    await update.message.reply_text(
        "✅ Foto Karpeg tersimpan. Ketik /karpeg untuk melihat kartu."
    )


# Filter untuk registrasi handler (chat privat saja).
KARPEG_PRIVATE = filters.ChatType.PRIVATE
