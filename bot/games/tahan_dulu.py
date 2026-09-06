import json
import random
import time
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

# PHASE CONSTANTS
PHASE_WAITING = "waiting"

# Command: /bermain tahan_dulu [setting_name] [delay_seconds]
async def mulai_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, args_text: str):
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
        setting_data = await db.get_game_setting(conn, "tahan_dulu", setting_name)
        if setting_data:
            valid_words = setting_data.get("valid_words", [])
            if valid_words:
                setting_display = f"\n(Hanya kata valid tertentu yang akan diterima)\n"
        else:
            await update.message.reply_text(f"Setting '{setting_name}' tidak ditemukan untuk Tahan Dulu.")
            return
    
    # Check if there is an active session
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini. Hentikan dulu dengan /berhenti {active['game_name']}.")
        return

    await update.message.reply_text(
        f"⏳ <b>GAME: Tahan Dulu</b> ⏳\n\n"
        f"Tahan dulu...\n"
        f"Balas pesan apapun SEBELUM <b>{delay_min} detik</b> = penalti (-2).\n"
        f"Setelah itu, yang merespons paling cepat dapat poin!\n"
        f"{setting_display}\n"
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
        "early": {},       # dict {user_id: {"name": "..."}}
        "responses": [],   # list [{"uid": user_id, "name": "...", "diff": float}]
        "scores": {}       # dict {user_id: {"name": "...", "score": int}} (accumulated if needed)
    }
    
    await db.start_game_session(conn, chat_id, "tahan_dulu", setting_name or "default", initial_state)
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return
        
    # Jadwalkan perpindahan ke end round (delay_min + 11 detik)
    context.job_queue.run_once(
        job_end_tahan_dulu,
        delay_min + 11,
        chat_id=chat_id,
        name=f"tahan_dulu_{chat_id}",
        data={"session_id": session["id"]}
    )

async def proses_pesan_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return # Sesi sudah berakhir
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_WAITING:
            return
            
        msg_text = update.effective_message.text or ""
        valid_words = state.get("valid_words", [])
        if valid_words:
            # Check if message matches any valid word
            is_valid = False
            for w in valid_words:
                if msg_text.strip().lower() == w:
                    is_valid = True
                    break
            if not is_valid:
                return # Ignore message
            
        user = update.effective_user
        uid_str = str(user.id)
        name = user.first_name or user.username or uid_str
        
        # 1 user cuma dinilai 1x
        if uid_str in state.get("early", {}):
            return
            
        for r in state.get("responses", []):
            if r["uid"] == uid_str:
                return
                
        now = time.time()
        start_time = state["start_time"]
        delay_min = state["delay_min"]
        
        diff = now - start_time
        
        if diff < delay_min:
            early = state.setdefault("early", {})
            early[uid_str] = {"name": name}
        else:
            responses = state.setdefault("responses", [])
            responses.append({
                "uid": uid_str,
                "name": name,
                "diff": diff
            })
            
        await db.update_game_session_state(conn, session_id, state)

async def job_end_tahan_dulu(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    async with lock:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["id"] != session_id or session["game_name"] != "tahan_dulu":
            return
            
        state = json.loads(session["state_json"])
        if state["phase"] != PHASE_WAITING:
            return
            
        # Kita hentikan sementara tapi kita bisa biarkan sesi tetap hidup untuk akumulasi skor?
        # Supaya tidak terus menangkap pesan, kita ubah status jadi "finished" atau matikan sesinya
        state["phase"] = "finished"
        
        early = state.get("early", {})
        responses = state.get("responses", [])
        scores = state.setdefault("scores", {})
        
        POINTS_AFTER = [5, 4, 3, 2, 1]
        lines = []
        
        # Penalti kepagian
        for uid_str, data in early.items():
            name = data["name"]
            user_score = scores.setdefault(uid_str, {"name": name, "score": 0})
            user_score["score"] -= 2
            lines.append(f"❌ {name}: kepagian (-2)")
            
        # Poin setelah delay
        # Sort based on diff
        responses.sort(key=lambda x: x["diff"])
        
        for i, r in enumerate(responses):
            uid_str = r["uid"]
            name = r["name"]
            diff = r["diff"]
            
            point = POINTS_AFTER[i] if i < len(POINTS_AFTER) else 0
            user_score = scores.setdefault(uid_str, {"name": name, "score": 0})
            user_score["score"] += point
            
            lines.append(f"✅ {name}: {diff:.2f}s (+{point})")
            
        # Susun Leaderboard Keseluruhan
        lb = []
        for uid_str, s in scores.items():
            lb.append(s)
        lb.sort(key=lambda x: x["score"], reverse=True)
        
        lb_lines = []
        for i, s in enumerate(lb[:5], 1):
            lb_lines.append(f"{i}. {s['name']} — {s['score']}")
            
        text = "⏱ <b>Hasil Ronde Tahan Dulu</b>\n\n"
        if lines:
            text += "\n".join(lines) + "\n\n"
        else:
            text += "😅 Tidak ada yang berpartisipasi.\n\n"
            
        text += "🏆 <b>Leaderboard (Top 5)</b>\n"
        if lb_lines:
            text += "\n".join(lb_lines)
        else:
            text += "Belum ada skor."
            
        text += "\n\n<i>Sesi telah dihentikan. Ketik /bermain tahan_dulu untuk memulai ronde baru.</i>"
        
        await db.update_game_session_state(conn, session_id, state)
        await db.end_game_session(conn, session_id)
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML"
    )

async def status_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    phase = state["phase"]
    
    if phase == PHASE_WAITING:
        msg = f"🎮 <b>Tahan Dulu</b> sedang berjalan!\nSedang dalam ronde menunggu respon."
    else:
        msg = "🎮 <b>Tahan Dulu</b> (Selesai)"
        
    await update.message.reply_text(msg, parse_mode="HTML")

async def berhenti_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "tahan_dulu":
            await update.message.reply_text("Tidak ada sesi Tahan Dulu yang aktif di grup ini.")
            return

    # Cancel jobs
    current_jobs = context.job_queue.get_jobs_by_name(f"tahan_dulu_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
        
    await db.end_game_session(conn, session["id"])
    await update.message.reply_text("⏹ Game Tahan Dulu telah dihentikan secara paksa.")

async def hasil_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    scores = state.get("scores", {})
    
    if not scores:
        await update.message.reply_text("Tidak ada hasil yang tersedia.")
        return
        
    lb = []
    for uid_str, s in scores.items():
        lb.append(s)
    lb.sort(key=lambda x: x["score"], reverse=True)
    
    lines = ["🏆 <b>Leaderboard Tahan Dulu (Akhir)</b>"]
    for i, s in enumerate(lb, 1):
        lines.append(f"{i}. {s['name']} — {s['score']}")
        
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def atur_tahan_dulu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, setting_name: str, args_text: str):
    if not args_text.strip():
        await update.message.reply_text(f"Gunakan: /atur tahan_dulu {setting_name} <kata1>, <kata2>, ...")
        return
        
    words = [w.strip().lower() for w in args_text.split(",") if w.strip()]
    if not words:
        await update.message.reply_text("Tidak ada kata valid yang terdeteksi.")
        return
        
    data = {"valid_words": words}
    await db.upsert_game_setting(conn, "tahan_dulu", setting_name, data)
    
    words_str = ", ".join(f"'{w}'" for w in words)
    await update.message.reply_text(
        f"✅ Setting <b>{setting_name}</b> untuk Tahan Dulu disimpan.\n"
        f"Kata Valid: {words_str}\n\n"
        f"Cara main: /bermain tahan_dulu {setting_name} [delay]",
        parse_mode="HTML"
    )
