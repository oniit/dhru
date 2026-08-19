from __future__ import annotations

import logging
import random
import string
import time
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from bot.database import Database

log = logging.getLogger(__name__)

# Temporary in-memory store for OTPs
# Format: { "PROMO-XYZ": {"main_user_id": 12345, "expires_at": 1700000000} }
OTP_STORE: dict[str, dict] = {}

def generate_otp() -> str:
    return "KERJA-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def link_kerja_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Silakan gunakan perintah ini di chat pribadi (DM).")
        return

    main_user_id = update.effective_user.id
    
    # Cleanup expired OTPs (optional, but good practice)
    now = time.time()
    expired = [k for k, v in OTP_STORE.items() if v["expires_at"] < now]
    for k in expired:
        OTP_STORE.pop(k, None)

    code = generate_otp()
    OTP_STORE[code] = {
        "main_user_id": main_user_id,
        "expires_at": now + 600  # valid for 10 minutes
    }

    text = (
        "🔗 **Tautkan Akun Kerja**\n\n"
        "Untuk menautkan akun kerjamu (akun promosi), ikuti langkah ini:\n"
        "1. Login ke akun kerjamu di Telegram.\n"
        f"2. Kirimkan pesan berisi kode di bawah ini ke bot ini secara langsung (DM):\n\n"
        f"<code>{code}</code>\n\n"
        "*(Kode ini hanya berlaku selama 10 menit)*"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cek_akun_kerja_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    main_user_id = update.effective_user.id
    
    linked_accounts = await db.get_linked_accounts(conn, main_user_id)
    if not linked_accounts:
        await update.message.reply_text("Kamu belum menautkan akun kerja apa pun. Gunakan /link_kerja untuk menautkan.")
        return

    text = "📋 **Daftar Akun Kerjamu yang Terdaftar:**\n\n"
    for idx, acc_id in enumerate(linked_accounts, start=1):
        text += f"{idx}. <code>{acc_id}</code>\n"
    text += "\nJika kamu menggunakan salah satu akun di atas untuk menyebar link promosi, saldo Agra akan tetap masuk ke akun utama ini."
    
    await update.message.reply_text(text, parse_mode="HTML")

async def lpm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Format salah! Gunakan: `/lpm <link_pesan>`\nContoh: `/lpm https://t.me/grup_lpm/123`")
        return
        
    link = context.args[0]
    if "t.me/" not in link:
        await update.message.reply_text("Link tidak valid. Pastikan link berasal dari Telegram (mengandung t.me).")
        return

    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    user_id = update.effective_user.id
    
    # Check if link exists
    exists = await db.check_promo_link_exists(conn, link)
    if exists:
        await update.message.reply_text("❌ Link ini sudah pernah diklaim sebelumnya.")
        return

    # Add to database
    await db.add_promo_verification(conn, user_id, link)
    
    await update.message.reply_text(
        "⏳ Link berhasil disubmit! Sistem sedang memvalidasi pesanmu. "
        "Jika valid, Agra akan otomatis masuk ke saldomu."
    )

async def handle_otp_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches OTP codes sent by promo accounts."""
    if not update.message or not update.message.text:
        return
        
    if update.effective_chat.type != "private":
        return

    text = update.message.text.strip().upper()
    if text.startswith("KERJA-") and len(text) == 12:
        now = time.time()
        otp_data = OTP_STORE.get(text)
        
        if not otp_data:
            await update.message.reply_text("❌ Kode OTP tidak valid atau salah ketik.")
            return
            
        if otp_data["expires_at"] < now:
            await update.message.reply_text("❌ Kode OTP sudah kedaluwarsa. Silakan minta ulang di akun utama.")
            OTP_STORE.pop(text, None)
            return
            
        main_user_id = otp_data["main_user_id"]
        promo_user_id = update.effective_user.id
        
        if main_user_id == promo_user_id:
            await update.message.reply_text("❌ Kamu mengirim kode dari akun utama yang sama. Harus dikirim dari akun kerja.")
            return

        db: Database = context.bot_data["db"]
        conn = context.bot_data["conn"]
        
        success = await db.add_linked_account(conn, main_user_id, promo_user_id)
        if success:
            await update.message.reply_text(
                "✅ **Berhasil!** Akun ini sekarang tertaut sebagai Akun Kerja.\n\n"
                "Mulai sekarang, semua link promosi yang dikirim oleh akun ini bisa diklaim menggunakan akun utama."
            )
            # Notifikasi ke akun utama
            try:
                await context.bot.send_message(
                    chat_id=main_user_id,
                    text=f"✅ Akun kerja dengan ID <code>{promo_user_id}</code> berhasil ditautkan ke akun utamamu!",
                    parse_mode="HTML"
                )
            except Exception as e:
                log.error(f"Gagal mengirim notif ke akun utama: {e}")
        else:
            await update.message.reply_text("❌ Akun ini sudah ditautkan ke akun utama tersebut sebelumnya.")
            
        OTP_STORE.pop(text, None)

def setup_promo_handlers(application) -> None:
    application.add_handler(CommandHandler("link_kerja", link_kerja_cmd))
    application.add_handler(CommandHandler("cek_akun_kerja", cek_akun_kerja_cmd))
    application.add_handler(CommandHandler("lpm", lpm_cmd))
    # Filter only text messages that start with KERJA-
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r"(?i)^KERJA-[A-Z0-9]{6}$"), handle_otp_message),
        group=1  # Put in group 1 so it doesn't conflict with main command handlers fallback
    )
