from telegram import Update
from telegram.ext import ContextTypes
import bot.games.kata_rahasia as kata_rahasia

def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]

def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]

def _is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    from bot.settings import ADMIN_IDS, OWNER_ID
    return user_id == OWNER_ID or user_id in ADMIN_IDS

# /atur <game_name> <setting_name> [args...]
async def cmd_atur(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
        
    if not _is_admin(update.effective_user.id, context):
        await update.message.reply_text("Tidak diizinkan.")
        return
        
    args = update.message.text.split(maxsplit=3)
    if len(args) < 4:
        await update.message.reply_text("Penggunaan: /atur <nama_game> <nama_setting> <konfigurasi...>")
        return
        
    game_name = args[1].lower()
    setting_name = args[2].lower()
    args_text = args[3]
    
    conn = _conn(context)
    db = _db(context)
    
    if game_name == "kata_rahasia":
        await kata_rahasia.atur_kata_rahasia(update, context, db, conn, setting_name, args_text)
    else:
        await update.message.reply_text(f"Game '{game_name}' tidak didukung.")

# /bermain <game_name> <setting_name>
async def cmd_bermain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
        
    if update.effective_chat.type == "private":
        await update.message.reply_text("Game hanya bisa dimainkan di grup.")
        return
        
        
    args = update.message.text.split(maxsplit=2)
    if len(args) < 3:
        await update.message.reply_text("Penggunaan: /bermain <nama_game> <nama_setting>")
        return
        
    game_name = args[1].lower()
    setting_name = args[2].lower()
    
    conn = _conn(context)
    db = _db(context)
    
    if game_name == "kata_rahasia":
        await kata_rahasia.mulai_kata_rahasia(update, context, db, conn, setting_name)
    else:
        await update.message.reply_text(f"Game '{game_name}' tidak didukung.")

# /status <game_name>
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or update.effective_chat.type == "private":
        await update.message.reply_text("Game hanya dimainkan di grup.")
        return
        
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text("Penggunaan: /status <nama_game>")
        return
        
    game_name = args[1].lower()
    conn = _conn(context)
    db = _db(context)
    
    session = await db.get_active_game_session(conn, update.effective_chat.id)
    if not session or session["game_name"] != game_name:
        await update.message.reply_text(f"Tidak ada sesi {game_name} yang aktif di grup ini.")
        return
        
    if game_name == "kata_rahasia":
        await kata_rahasia.status_kata_rahasia(update, context, db, conn, session)
    else:
        await update.message.reply_text(f"Game '{game_name}' tidak didukung.")

# /berhenti <game_name>
async def cmd_berhenti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or update.effective_chat.type == "private":
        return
        
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text("Penggunaan: /berhenti <nama_game>")
        return
        
    game_name = args[1].lower()
    conn = _conn(context)
    db = _db(context)
    
    session = await db.get_active_game_session(conn, update.effective_chat.id)
    if not session or session["game_name"] != game_name:
        await update.message.reply_text(f"Tidak ada sesi {game_name} yang aktif di grup ini.")
        return
        
    import json
    state = json.loads(session["state_json"])
    is_starter = (update.effective_user.id == state.get("started_by"))
    is_admin = _is_admin(update.effective_user.id, context)
    
    if not (is_starter or is_admin):
        await update.message.reply_text("Hanya admin atau pemulai game yang bisa menghentikan permainan.")
        return
        
    if game_name == "kata_rahasia":
        await kata_rahasia.berhenti_kata_rahasia(update, context, db, conn, session)
    else:
        await update.message.reply_text(f"Game '{game_name}' tidak didukung.")

async def process_game_message(conn, db, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called by messages.on_group_message for every natural message in a group.
    Returns True if a game processed it (or we should stop other handlers), False otherwise.
    """
    chat_id = update.effective_chat.id
    
    # In-memory cache checks can be implemented here if DB query per message is too heavy.
    # For MVP, we query the DB to get the active session.
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return False
        
    game_name = session["game_name"]
    if game_name == "kata_rahasia":
        await kata_rahasia.proses_pesan_kata_rahasia(update, context, db, conn, session)
        # We return False because natural messages shouldn't stop other listeners (like activity tracking)
        # unless specifically required by the game mechanics.
        return False
        
    return False
