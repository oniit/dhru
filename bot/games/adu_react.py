import json
import time
from telegram import Update
from telegram.ext import ContextTypes

async def mulai_adu_react(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, args_text: str):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    session = await db.get_active_game_session(conn, chat_id)
    if session:
        await update.message.reply_text(f"Masih ada game {session['game_name']} yang sedang berjalan di grup ini.")
        return
        
    state = {
        "started_by": user_id,
        "start_ts": time.time(),
        "start_message_id": update.message.message_id,
        "reactions": {}
    }
    
    await db.start_game_session(conn, chat_id, "adu_react", "default", state)
    
    await update.message.reply_text(
        "⚡ <b>Game Adu React dimulai!</b>\n\n"
        "Berikan react ke pesan apa saja! Pemenangnya adalah pesan dengan react terbanyak saat game dihentikan.\n"
        "Ketik <code>/berhenti adu_react</code> untuk mengakhiri permainan.",
        parse_mode="HTML"
    )

async def status_adu_react(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session):
    state = json.loads(session["state_json"])
    
    reactions = state.get("reactions", {})
    if not reactions:
        await update.message.reply_text("Game Adu React sedang berjalan, tapi belum ada yang memberi react.")
        return
        
    # Find current max
    max_react = -1
    for msg_id, data in reactions.items():
        if data["count"] > max_react:
            max_react = data["count"]
            
    await update.message.reply_text(f"Game Adu React sedang aktif!\nSaat ini react terbanyak adalah: <b>{max_react}</b> react.", parse_mode="HTML")

async def berhenti_adu_react(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session):
    chat_id = update.effective_chat.id
    state = json.loads(session["state_json"])
    reactions = state.get("reactions", {})
    
    if not reactions:
        await update.message.reply_text("Game dihentikan. Belum ada react yang masuk sama sekali.")
        await db.end_game_session(conn, chat_id, "adu_react")
        return
        
    winner_msg_id = None
    max_react = -1
    fastest_ts = float("inf")
    
    for msg_id_str, data in reactions.items():
        count = data["count"]
        # Skip if count <= 0
        if count <= 0:
            continue
            
        if count > max_react:
            winner_msg_id = int(msg_id_str)
            max_react = count
            fastest_ts = data["first_react_ts"]
        elif count == max_react:
            if data["first_react_ts"] < fastest_ts:
                winner_msg_id = int(msg_id_str)
                fastest_ts = data["first_react_ts"]
                
    if winner_msg_id is None:
        await update.message.reply_text("Game dihentikan. Semua react telah ditarik kembali.")
        await db.end_game_session(conn, chat_id, "adu_react")
        return
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⠀⠀⠀𖠹 ˙˙˙ congrats!  ༨𐂥⠀\n         🔥 total react: {max_react}",
        reply_to_message_id=winner_msg_id
    )
    
    # Save winner to state for history
    state["winner_msg_id"] = winner_msg_id
    state["max_react"] = max_react
    await db.update_game_session_state(conn, session["id"], state)
    
    await db.end_game_session(conn, chat_id, "adu_react")

async def hasil_adu_react(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session):
    state = json.loads(session["state_json"])
    winner_msg_id = state.get("winner_msg_id")
    max_react = state.get("max_react", 0)
    
    if winner_msg_id:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Hasil Adu React terakhir:\nIni adalah pesan pemenang dengan {max_react} react!",
            reply_to_message_id=winner_msg_id
        )
    else:
        await update.message.reply_text("Hasil Adu React terakhir: Tidak ada pemenang (tidak ada react/ditarik).")

async def proses_reaksi_adu_react(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session):
    """
    Called when a MessageReactionUpdated is received and an adu_react session is active.
    """
    reaction_update = update.message_reaction
    if not reaction_update:
        return
        
    chat_id = reaction_update.chat.id
    msg_id = reaction_update.message_id
    
    import asyncio
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        # Refetch state in case it changed
        current_session = await db.get_active_game_session(conn, chat_id)
        if not current_session or current_session["id"] != session_id:
            return
            
        state = json.loads(current_session["state_json"])
        
        # Only count reactions for messages sent after the game started
        start_message_id = state.get("start_message_id", 0)
        if msg_id <= start_message_id:
            return
            
        old_react = reaction_update.old_reaction
        new_react = reaction_update.new_reaction
        
        delta = len(new_react) - len(old_react)
        if delta == 0:
            return
            
        reactions = state.setdefault("reactions", {})
        msg_id_str = str(msg_id)
        
        if msg_id_str not in reactions:
            reactions[msg_id_str] = {
                "count": 0,
                "first_react_ts": time.time()
            }
            
        reactions[msg_id_str]["count"] += delta
        
        await db.update_game_session_state(conn, session_id, state)
