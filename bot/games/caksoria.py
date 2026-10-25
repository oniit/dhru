import json
import random
import time
import asyncio
import html
from telegram import Update
from telegram.ext import ContextTypes

# PHASE CONSTANTS
PHASE_WAITING = "waiting"
PHASE_FINISHED = "finished"


# Command: /bermain caksoria [setting_name] [delay_seconds]
async def mulai_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, args_text: str):
    chat_id = update.effective_chat.id
    
    # Parse delay and setting
    delay_min = None
    setting_name = None
    
    if args_text:
        parts = args_text.split()
        if len(parts) >= 2:
            setting_name = parts[0]
            try:
                delay_min = int(parts[1])
            except ValueError:
                pass
        elif len(parts) == 1:
            try:
                delay_min = int(parts[0])
            except ValueError:
                setting_name = parts[0]
                
    if not delay_min or delay_min <= 0:
        delay_min = random.randint(7, 17)
        
    valid_words = []
    setting_display = ""
    if setting_name:
        setting_data = await db.get_game_setting(conn, "caksoria", setting_name)
        if setting_data:
            valid_words = setting_data.get("valid_words", [])
            if valid_words:
                kw_str = ", ".join(f"<code>{html.escape(w)}</code>" for w in valid_words)
                setting_display = f"\nKeyword valid: {kw_str}\n"
        else:
            await update.message.reply_text(f"Setting '{setting_name}' tidak ditemukan untuk Caksoria.")
            return
    
    # Check if there is an active session
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(
            f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini. Hentikan dulu dengan /berhenti {active['game_name']}."
        )
        return

    await update.message.reply_text(
        f"⏳ <b>GAME: Caksoria</b> ⏳\n\n"
        f"Tahan dulu...\n"
        f"Jangan kirim pesan sebelum <b>{delay_min} detik</b>!\n"
        f"Penerimaan jawaban dibuka selama <b>30 detik</b> setelah waktu tahan.\n"
        #f"{setting_display}\n"
        f"<i>Waktu dimulai dari sekarang!</i>",
        parse_mode="HTML"
    )

    start_time = time.time()
    
    # Inisialisasi state
    initial_state = {
        "phase": PHASE_WAITING,
        "start_time": start_time,
        "delay_min": delay_min,
        "valid_words": valid_words,
        "entries": [],   # list [{"uid": str, "name": str, "diff": float, "text": str, "matches_keyword": bool, "emoji": str}]
        "user_ids": []   # list [str] memastikan 1 user hanya dinilai 1x (jawaban pertama)
    }
    
    await db.start_game_session(conn, chat_id, "caksoria", setting_name or "default", initial_state)
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return
        
    # Jadwalkan berakhirnya penerimaan jawaban (delay_min + 30 detik)
    context.job_queue.run_once(
        job_end_caksoria,
        delay_min + 30,
        chat_id=chat_id,
        name=f"caksoria_{chat_id}",
        data={"session_id": session["id"]}
    )


async def proses_pesan_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return  # Sesi sudah berakhir
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_WAITING:
            return
            
        user = update.effective_user
        if not user:
            return
            
        uid_str = str(user.id)
        user_ids = state.setdefault("user_ids", [])
        
        # 1 user cuma dinilai 1x (respons pertama yang dicatat)
        if uid_str in user_ids:
            return
            
        user_ids.append(uid_str)
        
        msg_text = update.effective_message.text or update.effective_message.caption or ""
        text_clean = msg_text.strip().lower()
        
        valid_words = state.get("valid_words", [])
        if valid_words:
            matches_keyword = any(text_clean == w.strip().lower() for w in valid_words)
        else:
            # Jika tidak ada setting kata khusus, semua format teks dianggap match keyword
            matches_keyword = True
            
        now = time.time()
        start_time = state["start_time"]
        delay_min = state["delay_min"]
        diff = now - start_time
        
        # Ketentuan emoji:
        # 🥳 yg sesuai keyword (dan tidak kecepetan)
        # 👺 yg kecepetan sama yg tidak sesuai format
        if diff < delay_min:
            emoji = "👺"
        elif not matches_keyword:
            emoji = "👺"
        else:
            emoji = "🥳"
            
        name = user.first_name or user.username or uid_str
        entries = state.setdefault("entries", [])
        entries.append({
            "uid": uid_str,
            "name": name,
            "diff": diff,
            "text": msg_text,
            "matches_keyword": matches_keyword,
            "emoji": emoji
        })
        
        await db.update_game_session_state(conn, session_id, state)


async def job_end_caksoria(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    async with lock:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["id"] != session_id or session["game_name"] != "caksoria":
            return
            
        state = json.loads(session["state_json"])
        if state["phase"] != PHASE_WAITING:
            return
            
        state["phase"] = PHASE_FINISHED
        entries = state.get("entries", [])
        
        # Urutkan berdasarkan waktu respon (diff) tercepat ke terlambat
        entries.sort(key=lambda x: x["diff"])
        
        lines = []
        for e in entries:
            clean_name = html.escape(e["name"])
            lines.append(f"{e['emoji']} {clean_name}: {e['diff']:.2f}s")
            
        text = "⏱ <b>Hasil Ronde Caksoria</b>\n\n"
        if lines:
            text += "\n".join(lines) + "\n\n"
            text += "<b>Keterangan:</b>\n"
            text += "🥳 Benar\n"
            text += "👺 Salah / belum waktunya\n\n"
        else:
            text += "😅 Tidak ada yang berpartisipasi.\n\n"
            
        text += "<i>Sesi telah selesai. Ketik /bermain caksoria untuk memulai ronde baru.</i>"
        
        await db.update_game_session_state(conn, session_id, state)
        await db.end_game_session(conn, session_id)
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML"
    )


async def status_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    phase = state["phase"]
    
    if phase == PHASE_WAITING:
        now = time.time()
        elapsed = now - state["start_time"]
        delay_min = state["delay_min"]
        entries_count = len(state.get("entries", []))
        msg = (
            f"🎮 <b>Caksoria</b> sedang berjalan!\n"
            f"Waktu berjalan: {elapsed:.1f}s (Waktu tahan: {delay_min}s, Batas terima: {delay_min + 30}s)\n"
            f"Total respon terdata: {entries_count} orang."
        )
    else:
        msg = "🎮 <b>Caksoria</b> (Selesai)"
        
    await update.message.reply_text(msg, parse_mode="HTML")


async def berhenti_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "caksoria":
            await update.message.reply_text("Tidak ada sesi Caksoria yang aktif di grup ini.")
            return

    # Cancel jobs
    current_jobs = context.job_queue.get_jobs_by_name(f"caksoria_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
        
    await db.end_game_session(conn, session["id"])
    await update.message.reply_text("⏹ Game Caksoria telah dihentikan secara paksa.")


async def hasil_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    entries = state.get("entries", [])
    
    if not entries:
        await update.message.reply_text("Tidak ada hasil yang tersedia.")
        return
        
    entries.sort(key=lambda x: x["diff"])
    lines = []
    for e in entries:
        clean_name = html.escape(e["name"])
        lines.append(f"{e['emoji']} {clean_name}: {e['diff']:.2f}s")
        
    text = "⏱ <b>Hasil Ronde Caksoria (Terakhir)</b>\n\n"
    text += "\n".join(lines) + "\n\n"
    text += "<b>Keterangan:</b>\n"
    text += "🥳 Benar\n"
    text += "👺 Salah / belum waktunya"
    
    await update.message.reply_text(text, parse_mode="HTML")


async def atur_caksoria(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, setting_name: str, args_text: str):
    if not args_text.strip():
        await update.message.reply_text(f"Gunakan: /atur caksoria {setting_name} <kata1>, <kata2>, ...")
        return
        
    words = [w.strip().lower() for w in args_text.split(",") if w.strip()]
    if not words:
        await update.message.reply_text("Tidak ada kata valid yang terdeteksi.")
        return
        
    data = {"valid_words": words}
    await db.upsert_game_setting(conn, "caksoria", setting_name, data)
    
    words_str = ", ".join(f"'{w}'" for w in words)
    await update.message.reply_text(
        f"✅ Setting <b>{setting_name}</b> untuk Caksoria disimpan.\n"
        f"Kata Valid: {words_str}\n\n"
        f"Cara main: /bermain caksoria {setting_name} [delay]",
        parse_mode="HTML"
    )
