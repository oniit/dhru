from telegram import Update
from telegram.ext import ContextTypes
import bot.games.kata_rahasia as kata_rahasia
import bot.games.kantong_rempah as kantong_rempah
import bot.games.tahan_dulu as tahan_dulu
import bot.games.adu_react as adu_react
import bot.games.tujuh_pusaka as tujuh_pusaka

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
        
        
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text(
            "🎮 <b>Daftar Mini-Games</b>\n"
            "• <code>/bermain kata_rahasia &lt;setting&gt;</code> — Tebak kata berkelompok\n"
            "• <code>/bermain kantong_rempah [menit]</code> — Tebak total rempah (via PC)\n"
            "• <code>/bermain tahan_dulu [detik]</code> — Adu cepat / reflex\n"
            "• <code>/bermain adu_react</code> — Balapan banyak-banyakan react\n"
            "• <code>/bermain tujuh_pusaka</code> — Card battle vs Bot\n",
            parse_mode="HTML"
        )
        return
        
    game_name = args[1].lower()
    setting_name = args[2].lower() if len(args) > 2 else "default"
    
    conn = _conn(context)
    db = _db(context)
    
    if game_name == "kata_rahasia":
        await kata_rahasia.mulai_kata_rahasia(update, context, db, conn, setting_name)
    elif game_name == "kantong_rempah":
        # kantong_rempah parses its own settings from args text
        args_text = " ".join(args[2:])
        await kantong_rempah.mulai_kantong_rempah(update, context, db, conn, args_text)
    elif game_name == "tahan_dulu":
        args_text = " ".join(args[2:])
        await tahan_dulu.mulai_tahan_dulu(update, context, db, conn, args_text)
    elif game_name == "adu_react":
        args_text = " ".join(args[2:])
        await adu_react.mulai_adu_react(update, context, db, conn, args_text)
    elif game_name == "tujuh_pusaka":
        await tujuh_pusaka.mulai_tujuh_pusaka(update, context, db, conn)
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
    elif game_name == "kantong_rempah":
        await kantong_rempah.status_kantong_rempah(update, context, db, conn, session)
    elif game_name == "tahan_dulu":
        await tahan_dulu.status_tahan_dulu(update, context, db, conn, session)
    elif game_name == "adu_react":
        await adu_react.status_adu_react(update, context, db, conn, session)
    elif game_name == "tujuh_pusaka":
        await tujuh_pusaka.status_tujuh_pusaka(update, context, db, conn, session)
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
    elif game_name == "kantong_rempah":
        await kantong_rempah.berhenti_kantong_rempah(update, context, db, conn, session)
    elif game_name == "tahan_dulu":
        await tahan_dulu.berhenti_tahan_dulu(update, context, db, conn, session)
    elif game_name == "adu_react":
        await adu_react.berhenti_adu_react(update, context, db, conn, session)
    elif game_name == "tujuh_pusaka":
        await tujuh_pusaka.berhenti_tujuh_pusaka(update, context, db, conn, session)
    else:
        await update.message.reply_text(f"Game '{game_name}' tidak didukung.")

# /hasil <game_name>
async def cmd_hasil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or update.effective_chat.type == "private":
        await update.message.reply_text("Game hanya dimainkan di grup.")
        return
        
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text("Penggunaan: /hasil <nama_game>")
        return
        
    game_name = args[1].lower()
    conn = _conn(context)
    db = _db(context)
    
    session = await db.get_last_ended_game_session(conn, update.effective_chat.id, game_name)
    if not session:
        await update.message.reply_text(f"Tidak ada histori game {game_name} yang sudah selesai di grup ini.")
        return
        
    if game_name == "kata_rahasia":
        await kata_rahasia.hasil_kata_rahasia(update, context, db, conn, session)
    elif game_name == "kantong_rempah":
        await kantong_rempah.hasil_kantong_rempah(update, context, db, conn, session)
    elif game_name == "tahan_dulu":
        await tahan_dulu.hasil_tahan_dulu(update, context, db, conn, session)
    elif game_name == "adu_react":
        await adu_react.hasil_adu_react(update, context, db, conn, session)
    elif game_name == "tujuh_pusaka":
        await tujuh_pusaka.hasil_tujuh_pusaka(update, context, db, conn, session)
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
    elif game_name == "kantong_rempah":
        return False
    elif game_name == "tahan_dulu":
        # Tahan dulu intercepts ANY text message during WAITING phase
        text = update.message.text or update.message.caption or ""
        if text.strip():
            await tahan_dulu.proses_pesan_tahan_dulu(update, context, db, conn, session)
        return False
    elif game_name == "tujuh_pusaka":
        # Tujuh pusaka has commands like /ikut, /mulai_game, /pusaka that start with /
        # If the dispatcher passes it here (assuming commands aren't exclusively caught by a CommandHandler),
        # we can process them here. However, typical telegram bots handle commands via CommandHandler.
        # But wait, other games also do it. Let's just process it.
        await tujuh_pusaka.proses_pesan_tujuh_pusaka(update, context, db, conn, session)
        return False
        
    return False

# /tebak <angka>
async def cmd_tebak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or update.effective_chat.type == "private":
        return
        
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        return
        
    conn = _conn(context)
    db = _db(context)
    
    session = await db.get_active_game_session(conn, update.effective_chat.id)
    if not session:
        return
        
    if session["game_name"] == "kantong_rempah":
        text = update.message.text.strip()
        await kantong_rempah.proses_tebakan_grup(update, context, db, conn, session, text)

async def cmd_tujuh_pusaka_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or update.effective_chat.type == "private":
        return
        
    conn = _conn(context)
    db = _db(context)
    
    session = await db.get_active_game_session(conn, update.effective_chat.id)
    if not session:
        return
        
    if session["game_name"] == "tujuh_pusaka":
        await tujuh_pusaka.proses_pesan_tujuh_pusaka(update, context, db, conn, session)

async def on_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn(context)
    db = _db(context)
    if not update.message_reaction:
        return
        
    chat_id = update.message_reaction.chat.id
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return
        
    game_name = session["game_name"]
    if game_name == "adu_react":
        await adu_react.proses_reaksi_adu_react(update, context, db, conn, session)
