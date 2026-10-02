import html
import logging
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import warnings
from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning, message="If 'per_message=False'")

from bot.database import Database
from bot.settings import MANOS_CH_ID

log = logging.getLogger(__name__)

# States
MESSAGE, CONFIRM = range(2)

def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]

def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]

async def cmd_manosraya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from bot.handlers.common import rate_limit_check
    if not update.effective_user or not rate_limit_check(update.effective_user.id, "manosraya", 3):
        await update.message.reply_text("❌ Jangan spam! Tunggu beberapa detik sebelum mengakses menu lagi.")
        return ConversationHandler.END
        
    await update.message.reply_text(
        "<b>Yaksa Open Arms</b> 🕊️\n\n"
        "Silakan ketik aspirasi, kritik, atau saran untuk Dhruva.\n"
        "Pesan Anda akan dikirim secara anonim ke channel, namun tetap tercatat di sistem kami untuk keperluan moderasi jika diperlukan.\n\n"
        "<i>Ketik /cancel untuk membatalkan.</i>",
        parse_mode="HTML"
    )
    return MESSAGE

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("Dibatalkan.")
        return ConversationHandler.END
        
    if len(text) > 4000:
        await update.message.reply_text(
            "⚠️ Pesan terlalu panjang (maksimal 4000 karakter).\n"
            "Silakan ketik ulang dengan lebih singkat, atau /cancel untuk membatalkan."
        )
        return MESSAGE
        
    context.user_data["manos_message"] = text
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Kirim", callback_data="manos:yes")],
        [InlineKeyboardButton("❌ Batal", callback_data="manos:cancel")]
    ]
    await update.message.reply_text(
        "Pesan aspirasi sudah siap. Apakah Anda yakin ingin mengirimkannya?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def on_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "manos:cancel":
        await query.message.edit_text("Pengiriman dibatalkan.")
        return ConversationHandler.END
        
    if data == "manos:yes":
        return await execute_manosraya(update, context)

async def execute_manosraya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sender_id = update.effective_user.id
    message_text = context.user_data.get("manos_message")
    
    db = _db(context)
    conn = _conn(context)
    
    # Record history
    manos_id = await db.add_manosraya(
        conn,
        sender_id=sender_id,
        message_text=message_text
    )
    
    # Send to channel
    channel_id = MANOS_CH_ID
    if not channel_id:
        await update.callback_query.message.edit_text("❌ Sistem belum dikonfigurasi dengan channel manosraya (Yaksa Open Arms). Silakan hubungi admin.")
        return ConversationHandler.END

    safe_message = html.escape(message_text)
    channel_msg = f"<b>Yaksa Open Arms</b> #{manos_id}\n\n{safe_message}"
        
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=channel_msg,
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Failed to send manosraya to channel: {e}")
        await update.callback_query.message.edit_text("❌ Gagal mengirim pesan ke channel. Silakan coba lagi nanti.")
        return ConversationHandler.END
        
    success_msg = f"✅ Pesan berhasil dikirim secara anonim ke Yaksa Open Arms!\nTerima kasih atas aspirasi Anda."
        
    await update.callback_query.message.edit_text(success_msg, disable_web_page_preview=True)
        
    return ConversationHandler.END

cmd_manosraya_router = ConversationHandler(
    entry_points=[CommandHandler("manosraya", cmd_manosraya)],
    states={
        MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler), CommandHandler("cancel", message_handler)],
        CONFIRM: [CallbackQueryHandler(on_confirm_callback, pattern="^manos:")],
    },
    fallbacks=[
        CommandHandler("cancel", lambda u, c: ConversationHandler.END),
        MessageHandler(filters.COMMAND, lambda u, c: ConversationHandler.END)
    ],
    per_chat=True,
    per_user=True,
)
