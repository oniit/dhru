"""Perintah /kartu, /foto — gambar ID Card KTM/Karpeg (hanya chat privat)."""

from __future__ import annotations

import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes, filters, CommandHandler, MessageHandler

from bot.database import ROLE_PUBLIC, ROLE_STUDENT, ROLE_BEM, ROLE_INTERNAL
from bot.ktm_card import render_ktm_png_bytes
from bot.karpeg_card import render_karpeg_png_bytes

from .common import profile_from_row, user_row

log = logging.getLogger(__name__)

# Step onboarding: tunggu satu foto dari user.
STEP_KARTU_PHOTO = "KARTU_PHOTO"


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
        log.warning("Unduh foto gagal file_id=%s", file_id[:20], exc_info=True)
        return None


async def cmd_kartu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    
    role = row["role"]
    if role == ROLE_PUBLIC:
        await update.message.reply_text("Selesaikan pendaftaran dulu (kode akses / profil).")
        return

    profile = profile_from_row(row)
    agra = await db.agra_total(conn, uid)
    photo_bytes: bytes | None = None
    fid = (profile.get("photo_file_id") or "").strip()
    if fid:
        photo_bytes = await _download_telegram_photo(context, fid)

    try:
        if role in (ROLE_INTERNAL, "admin", "owner"):
            png = render_karpeg_png_bytes(
                telegram_id=uid,
                profile=profile,
                agra=agra,
                role=role,
                use_cache=True,
                photo_bytes=photo_bytes,
            )
        else:
            png = render_ktm_png_bytes(
                telegram_id=uid,
                profile=profile,
                agra=agra,
                use_cache=True,
                photo_bytes=photo_bytes,
            )
    except FileNotFoundError as e:
        await update.message.reply_text(f"Template Kartu belum siap: {e}")
        return
    except Exception:
        log.exception("render Kartu gagal uid=%s", uid)
        await update.message.reply_text("Gagal membuat gambar Kartu. Coba lagi nanti.")
        return

    cap = "Kirim /foto untuk mengatur atau mengganti foto."
    if fid and photo_bytes is None:
        cap += " (Foto lama tidak bisa diunduh — kirim ulang dengan /foto.)"

    await update.message.reply_photo(
        photo=BytesIO(png),
        filename="kartu.png",
        caption=cap,
    )


async def cmd_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text(
            "/foto hanya bisa digunakan di chat privat dengan bot."
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

    await db.set_onboarding_step(conn, uid, STEP_KARTU_PHOTO)
    await update.message.reply_text(
        "Kirim <b>satu foto</b> (wajah) di chat ini. Foto akan dipotong secara otomatis.\n\n"
        "Setelah tersimpan, ketik /kartu untuk melihat hasilnya.\n"
        "Anda dapat mengirim foto baru lagi kapan saja dengan <code>/foto</code> untuk mengganti."
    )


async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if step != STEP_KARTU_PHOTO:
        return
    if row["role"] == ROLE_PUBLIC:
        await db.set_onboarding_step(conn, uid, None)
        return

    photos = update.message.photo
    largest = photos[-1]
    file_id = largest.file_id

    await db.set_profile_partial(conn, uid, {"photo_file_id": file_id})
    await db.set_onboarding_step(conn, uid, None)
    await update.message.reply_text(
        "✅ Foto tersimpan. Ketik /kartu untuk melihat hasilnya."
    )

# Filter untuk registrasi handler (chat privat saja).
KARTU_PRIVATE = filters.ChatType.PRIVATE
