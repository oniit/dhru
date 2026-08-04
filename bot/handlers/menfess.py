from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from bot.database import Database
from bot.settings import MENFESS_CH_ID

log = logging.getLogger(__name__)

# States
SUBMENU, TARGET, MESSAGE, CONFIRM, GIFT_AMOUNT = range(5)

def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]

def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]

async def cmd_menfess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("Kirim Menfess", callback_data="menfess:send")],
        [InlineKeyboardButton("History Masuk", callback_data="menfess:inbox"),
         InlineKeyboardButton("History Keluar", callback_data="menfess:outbox")],
        [InlineKeyboardButton("Batal", callback_data="menfess:cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(
            "<b>💌 Menu Menfess</b>\n\nSilakan pilih menu di bawah ini:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        await update.callback_query.message.edit_text(
            "<b>💌 Menu Menfess</b>\n\nSilakan pilih menu di bawah ini:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    return SUBMENU

async def on_submenu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "menfess:cancel":
        await query.message.edit_text("Operasi dibatalkan.")
        return ConversationHandler.END
        
    db = _db(context)
    conn = _conn(context)
    user_id = update.effective_user.id
    
    if data == "menfess:send":
        # Check agra balance first
        agra_total = await db.agra_total(conn, user_id)
        if agra_total < 1:
            await query.message.edit_text("❌ Saldo Agra Anda tidak mencukupi (minimal 1 Agra).")
            return ConversationHandler.END
            
        await query.message.edit_text(
            "Silakan masukkan username (contoh: @username) atau ID pengguna yang ingin dikirimi menfess:\n\n"
            "/cancel untuk membatalkan."
        )
        return TARGET
        
    elif data == "menfess:inbox":
        history = await db.get_menfess_inbox(conn, user_id)
        if not history:
            await query.message.edit_text("Tidak ada history menfess masuk.")
            return ConversationHandler.END
            
        text = "<b>📥 History Menfess Masuk</b>\n\n"
        for i, row in enumerate(history[:20], 1):
            text += f"{i}. ID: <code>{row['id']}</code> (Gift: {row['gift_agra']} agra)\n"
        text += "\nKetik <code>/menfess_read &lt;ID&gt;</code> untuk membaca isi pesan."
        await query.message.edit_text(text, parse_mode="HTML")
        return ConversationHandler.END
        
    elif data == "menfess:outbox":
        history = await db.get_menfess_sent(conn, user_id)
        if not history:
            await query.message.edit_text("Tidak ada history menfess keluar.")
            return ConversationHandler.END
            
        text = "<b>📤 History Menfess Keluar</b>\n\n"
        for i, row in enumerate(history[:20], 1):
            text += f"{i}. ID: <code>{row['id']}</code> (Ke: {row['receiver_id']})\n"
        text += "\nKetik <code>/menfess_read &lt;ID&gt;</code> untuk membaca isi pesan."
        await query.message.edit_text(text, parse_mode="HTML")
        return ConversationHandler.END

async def target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("Dibatalkan.")
        return ConversationHandler.END
        
    db = _db(context)
    conn = _conn(context)
    
    target_query = text
    if not target_query.isdigit() and not target_query.startswith("@"):
        target_query = f"@{target_query}"
        
    target_row = await db.get_user_by_username_or_id(conn, target_query)
    
    if not target_row:
        await update.message.reply_text(
            "⚠️ Pengguna tidak ditemukan atau belum terdaftar di bot.\n"
            "Silakan masukkan username / ID yang benar, atau ketik /cancel untuk membatalkan."
        )
        return TARGET
        
    if target_row["telegram_id"] == update.effective_user.id:
        await update.message.reply_text(
            "⚠️ Anda tidak bisa mengirim menfess ke diri sendiri.\n"
            "Silakan masukkan pengguna lain."
        )
        return TARGET
        
    context.user_data["menfess_target_id"] = target_row["telegram_id"]
    await update.message.reply_text(
        "✅ Target ditemukan.\n\n"
        "Sekarang, silakan ketik pesan menfess yang ingin dikirimkan:\n\n"
        "/cancel untuk membatalkan."
    )
    return MESSAGE

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("Dibatalkan.")
        return ConversationHandler.END
        
    context.user_data["menfess_message"] = text
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Kirim", callback_data="confirm:yes")],
        [InlineKeyboardButton("🎁 Tambah Gift", callback_data="confirm:gift")],
        [InlineKeyboardButton("❌ Batal", callback_data="confirm:cancel")]
    ]
    await update.message.reply_text(
        "Pesan menfess sudah siap.\n"
        "Biaya pengiriman: <b>1 Agra</b>.\n\n"
        "Apakah Anda yakin ingin mengirimkannya?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return CONFIRM

async def on_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "confirm:cancel":
        await query.message.edit_text("Pengiriman dibatalkan.")
        return ConversationHandler.END
        
    if data == "confirm:gift":
        await query.message.edit_text(
            "Berapa jumlah Agra yang ingin diberikan sebagai gift?\n\n"
            "Ketik nominal angkanya, atau /cancel untuk membatalkan."
        )
        return GIFT_AMOUNT
        
    if data == "confirm:yes":
        context.user_data["menfess_gift"] = 0
        return await execute_menfess(update, context)

async def gift_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("Dibatalkan.")
        return ConversationHandler.END
        
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Nominal tidak valid. Harap masukkan angka yang lebih dari 0.")
        return GIFT_AMOUNT
        
    gift = int(text)
    
    # Check balance again
    db = _db(context)
    conn = _conn(context)
    agra_total = await db.agra_total(conn, update.effective_user.id)
    if agra_total < (1 + gift):
        await update.message.reply_text(
            f"❌ Saldo Agra Anda tidak mencukupi.\n"
            f"Anda membutuhkan {1 + gift} Agra (1 biaya + {gift} gift), tapi saldo Anda {agra_total}.\n\n"
            f"Silakan masukkan nominal yang lebih kecil, atau /cancel."
        )
        return GIFT_AMOUNT
        
    context.user_data["menfess_gift"] = gift
    return await execute_menfess(update, context, is_message=True)

async def execute_menfess(update: Update, context: ContextTypes.DEFAULT_TYPE, is_message: bool = False) -> int:
    sender_id = update.effective_user.id
    target_id = context.user_data.get("menfess_target_id")
    message_text = context.user_data.get("menfess_message")
    gift = context.user_data.get("menfess_gift", 0)
    
    total_deduct = 1 + gift
    db = _db(context)
    conn = _conn(context)
    
    agra_total = await db.agra_total(conn, sender_id)
    if agra_total < total_deduct:
        msg = f"❌ Saldo Agra Anda tidak mencukupi. Butuh {total_deduct} Agra."
        if is_message:
            await update.message.reply_text(msg)
        else:
            await update.callback_query.message.edit_text(msg)
        return ConversationHandler.END
        
    # Get receiver name for channel message
    target_row = await db.get_user(conn, target_id)
    target_name = "Pengguna"
    if target_row:
        target_name = (f"{target_row['first_name'] or ''} {target_row['last_name'] or ''}").strip()
        if not target_name:
            target_name = target_row['username'] or str(target_id)
            
    gift_text = f" [Hadiah: {gift} agra]" if gift > 0 else ""
    
    # Send to channel FIRST
    channel_id = MENFESS_CH_ID
    channel_msg = f"{target_name} 💌 {message_text}{gift_text}"
        
    sent_msg = None
    post_link = ""
    try:
        sent_msg = await context.bot.send_message(
            chat_id=channel_id,
            text=channel_msg,
            parse_mode="HTML"
        )
        if sent_msg.chat.username:
            post_link = f"https://t.me/{sent_msg.chat.username}/{sent_msg.message_id}"
        else:
            cid = str(sent_msg.chat.id).replace("-100", "")
            post_link = f"https://t.me/c/{cid}/{sent_msg.message_id}"
    except Exception as e:
        log.error(f"Failed to send menfess to channel: {e}")
        fail_msg = "❌ Gagal mengirim menfess ke channel. Saldo Anda tidak dipotong. Silakan coba lagi nanti."
        if is_message:
            await update.message.reply_text(fail_msg)
        else:
            await update.callback_query.message.edit_text(fail_msg)
        return ConversationHandler.END

    # Deduct from sender
    await db.add_agra(
        conn,
        target_telegram_id=sender_id,
        actor_telegram_id=sender_id,
        amount=-total_deduct,
        description=f"Menfess payment (1) + gift ({gift})"
    )
    
    # Add to receiver (if gift > 0)
    if gift > 0:
        await db.add_agra(
            conn,
            target_telegram_id=target_id,
            actor_telegram_id=sender_id,
            amount=gift,
            description="Menfess gift"
        )
        
    # Record history
    menfess_id = await db.add_menfess(
        conn,
        sender_id=sender_id,
        receiver_id=target_id,
        message_text=message_text,
        gift_agra=gift
    )
    
    # Send to receiver's private chat
    private_msg = f"💌 {message_text}{gift_text}\n"
        
    if post_link:
        private_msg += f"\nLihat di channel @DhruvaFess: {post_link}"
    else:
        private_msg += "\nLihat di channel @DhruvaFess."
        
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=private_msg,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        log.error(f"Failed to send menfess to private chat {target_id}: {e}")
        
    success_msg = f"✅ Menfess berhasil dikirim! Saldo Anda terpotong {total_deduct} Agra."
    if post_link:
        success_msg += f"\nLink post: {post_link}"
        
    if is_message:
        await update.message.reply_text(success_msg, disable_web_page_preview=True)
    else:
        await update.callback_query.message.edit_text(success_msg, disable_web_page_preview=True)
        
    return ConversationHandler.END

async def cmd_menfess_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Penggunaan: /menfess_read <ID>")
        return
        
    try:
        menfess_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID menfess harus berupa angka.")
        return
        
    db = _db(context)
    conn = _conn(context)
    user_id = update.effective_user.id
    
    row = await db.get_menfess_by_id(conn, menfess_id)
    if not row:
        await update.message.reply_text("Menfess tidak ditemukan.")
        return
        
    if row["sender_id"] != user_id and row["receiver_id"] != user_id:
        await update.message.reply_text("Anda tidak berhak membaca menfess ini.")
        return
        
    text = (
        f"<b>💌 Menfess #{row['id']}</b>\n"
        f"Dari: <code>{row['sender_id']}</code>\n"
        f"Ke: <code>{row['receiver_id']}</code>\n"
        f"Waktu: {row['created_at']}\n"
        f"Gift Agra: {row['gift_agra']}\n\n"
        f"Pesan:\n{row['message_text']}"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")

cmd_menfess_router = ConversationHandler(
    entry_points=[CommandHandler("menfess", cmd_menfess)],
    states={
        SUBMENU: [CallbackQueryHandler(on_submenu_callback, pattern="^menfess:")],
        TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_handler), CommandHandler("cancel", target_handler)],
        MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler), CommandHandler("cancel", message_handler)],
        CONFIRM: [CallbackQueryHandler(on_confirm_callback, pattern="^confirm:")],
        GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_amount_handler), CommandHandler("cancel", gift_amount_handler)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
)
