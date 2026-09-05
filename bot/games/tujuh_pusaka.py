import json
import random
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

# PHASE CONSTANTS
PHASE_REGISTRATION = "registration"
PHASE_PLAYING = "playing"
PHASE_FINISHED = "finished"

CARDS = {
    "dika": {"name": "Dika / Rektor", "base_str": 90, "type": "rektor"},
    "nivia": {"name": "Nivia", "base_str": 75, "type": "wakil_rektor"},
    "nuansa": {"name": "Nuansa", "base_str": 75, "type": "wakil_rektor"},
    "leony": {"name": "Leony", "base_str": 60, "type": "sekretaris"},
    "dyah": {"name": "Dyah", "base_str": 60, "type": "sekretaris"},
    "neil": {"name": "Neil", "base_str": 60, "type": "sekretaris"},
    "pusaka": {"name": "Kartu Pusaka", "base_str": 0, "type": "pusaka"},
}

CARD_INFO = """
📜 <b>Tujuh Pusaka</b>
1. <b>Dika</b> (Str 90) - +15 Str vs Nivia/Nuansa.
2. <b>Nivia</b> (Str 75) - +20 Str vs kartu Str lebih tinggi, dan target kehilangan bonus Str-nya.
3. <b>Nuansa</b> (Str 75) - +20 Str vs Leony/Dyah/Neil.
4. <b>Leony</b> (Str 60) - Menyalin Power lawan, Str tetap 60.
5. <b>Dyah</b> (Str 60) - Membatalkan seluruh bonus Str lawan.
6. <b>Neil</b> (Str 60) - Jika kalah, Str lawan -20 di ronde berikutnya.
7. <b>Pusaka</b> (Str -) - Membalikkan hasil duel (Menang jadi Kalah, Kalah jadi Menang). Pusaka vs Pusaka = Draw.
"""

async def mulai_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn):
    chat_id = update.effective_chat.id
    
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini.")
        return

    initial_state = {
        "phase": PHASE_REGISTRATION,
        "started_by": update.effective_user.id,
        "players": {}, # uid -> {"name": "...", "cards": [...], "wins": 0, "next_round_penalty": 0}
        "bot_cards": list(CARDS.keys()),
        "round": 0,
        "choices": {} # uid -> card_id
    }
    
    await db.start_game_session(conn, chat_id, "tujuh_pusaka", "default", initial_state)
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return
    
    await update.message.reply_text(
        f"🎮 <b>Tujuh Pusaka</b> dibuka!\n\n"
        f"Ketik <code>/ikut</code> untuk bergabung ke dalam permainan.\n"
        f"Jika sudah siap, admin atau pembuat room bisa mengetik <code>/mulai_game</code> untuk memulai ronde pertama.\n"
        f"<i>Permainan akan otomatis dimulai dalam 3 menit.</i>\n\n"
        f"{CARD_INFO}",
        parse_mode="HTML"
    )

    # Jadwalkan reminder dan auto start
    context.job_queue.run_once(job_tujuh_pusaka_reminder, 120, chat_id=chat_id, name=f"tp_rem1_{chat_id}", data={"session_id": session["id"], "text": "⏳ <b>Tujuh Pusaka</b>: 1 menit lagi permainan akan otomatis dimulai!"})
    context.job_queue.run_once(job_tujuh_pusaka_reminder, 150, chat_id=chat_id, name=f"tp_rem2_{chat_id}", data={"session_id": session["id"], "text": "⏳ <b>Tujuh Pusaka</b>: 30 detik lagi!"})
    context.job_queue.run_once(job_tujuh_pusaka_reminder, 165, chat_id=chat_id, name=f"tp_rem3_{chat_id}", data={"session_id": session["id"], "text": "⏳ <b>Tujuh Pusaka</b>: 15 detik lagi!"})
    context.job_queue.run_once(job_tujuh_pusaka_autostart, 180, chat_id=chat_id, name=f"tp_auto_{chat_id}", data={"session_id": session["id"]})

async def job_tujuh_pusaka_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    text = job.data["text"]
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session or session["id"] != session_id: return
        
    state = json.loads(session["state_json"])
    if state["phase"] != PHASE_REGISTRATION: return
        
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

async def job_tujuh_pusaka_round_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    text = job.data["text"]
    session_id = job.data["session_id"]
    round_num = job.data["round"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session or session["id"] != session_id: return
        
    state = json.loads(session["state_json"])
    if state["phase"] != PHASE_PLAYING or state["round"] != round_num: return
        
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

async def job_tujuh_pusaka_autostart(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["id"] != session_id: return
            
        state = json.loads(session["state_json"])
        if state["phase"] != PHASE_REGISTRATION: return
            
        if not state["players"]:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Waktu habis, tetapi permainan dibatalkan karena belum ada pemain yang mendaftar.")
            await db.end_game_session(conn, chat_id, "tujuh_pusaka")
            return
            
        state["phase"] = PHASE_PLAYING
        state["round"] = 1
        
        await db.update_game_session_state(conn, session_id, state)
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⚔️ <b>Permainan Dimulai Secara Otomatis!</b>\n\n"
            f"<b>Ronde 1</b>\n"
            f"Silakan setiap pemain memilih 1 kartu dengan mengetik:\n"
            f"<code>/pusaka &lt;nama_kartu&gt;</code> (Contoh: <code>/pusaka dika</code>)\n\n"
            f"Sistem akan langsung memproses ronde jika semua pemain telah memilih."
        ),
        parse_mode="HTML"
    )
    
    # Auto timeout for round
    context.job_queue.run_once(
        job_timeout_round,
        120, # 2 minutes per round max
        chat_id=chat_id,
        name=f"tujuh_pusaka_timeout_{chat_id}",
        data={"session_id": session_id, "round": 1}
    )
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 60, chat_id=chat_id, name=f"tpr_rem1_{chat_id}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 1 menit lagi! Segera pilih kartu Anda."})
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 90, chat_id=chat_id, name=f"tpr_rem2_{chat_id}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 30 detik lagi!"})
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 105, chat_id=chat_id, name=f"tpr_rem3_{chat_id}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 15 detik lagi!"})

async def ikut_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_REGISTRATION:
            return
            
        user = update.effective_user
        uid_str = str(user.id)
        
        if uid_str in state["players"]:
            await update.message.reply_text(f"{user.first_name}, Anda sudah terdaftar.")
            return
            
        state["players"][uid_str] = {
            "name": user.first_name,
            "cards": list(CARDS.keys()),
            "wins": 0,
            "next_round_penalty": 0,
            "bot_next_round_penalty": 0
        }
        
        await db.update_game_session_state(conn, session_id, state)
        
    await update.message.reply_text(f"✅ {user.first_name} berhasil ikut Tujuh Pusaka! ({len(state['players'])} pemain)")

async def paksa_mulai_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_REGISTRATION:
            return
            
        if not state["players"]:
            await update.message.reply_text("Belum ada yang mendaftar!")
            return
            
        state["phase"] = PHASE_PLAYING
        state["round"] = 1
        
        await db.update_game_session_state(conn, session_id, state)
    
    await update.message.reply_text(
        f"⚔️ <b>Permainan Dimulai!</b>\n\n"
        f"<b>Ronde 1</b>\n"
        f"Silakan setiap pemain memilih 1 kartu dengan mengetik:\n"
        f"<code>/pusaka &lt;nama_kartu&gt;</code> (Contoh: <code>/pusaka dika</code>)\n\n"
        f"Sistem akan langsung memproses ronde jika semua pemain telah memilih.",
        parse_mode="HTML"
    )
    
    # Auto timeout for round
    context.job_queue.run_once(
        job_timeout_round,
        120, # 2 minutes per round max
        chat_id=session["chat_id"],
        name=f"tujuh_pusaka_timeout_{session['chat_id']}",
        data={"session_id": session_id, "round": 1}
    )
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 60, chat_id=session["chat_id"], name=f"tpr_rem1_{session['chat_id']}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 1 menit lagi! Segera pilih kartu Anda."})
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 90, chat_id=session["chat_id"], name=f"tpr_rem2_{session['chat_id']}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 30 detik lagi!"})
    context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 105, chat_id=session["chat_id"], name=f"tpr_rem3_{session['chat_id']}", data={"session_id": session_id, "round": 1, "text": "⏳ <b>Ronde 1</b>: 15 detik lagi!"})

async def proses_pesan_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip().lower()
    
    parts = text.split()
    if not parts:
        return
        
    cmd = parts[0]
    
    if cmd == "/ikut" or cmd.startswith("/ikut@"):
        await ikut_tujuh_pusaka(update, context, db, conn, session)
        return
        
    if cmd == "/mulai_game" or cmd.startswith("/mulai_game@"):
        state = json.loads(session["state_json"])
        if update.effective_user.id == state.get("started_by") or update.effective_user.id in context.application.bot_data.get("ADMIN_IDS", []):
            await paksa_mulai_tujuh_pusaka(update, context, db, conn, session)
        return
        
    if cmd == "/pusaka" or cmd.startswith("/pusaka@"):
        if len(parts) < 2: return
        card_choice = parts[1]
        await pilih_kartu(update, context, db, conn, session, card_choice)

async def pilih_kartu(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict, card_choice: str):
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_PLAYING:
            return
            
        uid_str = str(update.effective_user.id)
        if uid_str not in state["players"]:
            return
            
        if card_choice not in CARDS:
            await update.message.reply_text(f"⚠️ {card_choice} bukan kartu yang valid. (Pilih: dika, nivia, nuansa, leony, dyah, neil, pusaka)")
            return
            
        player_data = state["players"][uid_str]
        if card_choice not in player_data["cards"]:
            await update.message.reply_text(f"⚠️ {player_data['name']}, Anda sudah menggunakan kartu {card_choice}!")
            return
            
        if uid_str in state["choices"]:
            await update.message.reply_text(f"⚠️ {player_data['name']}, Anda sudah memilih kartu ronde ini!")
            return
            
        state["choices"][uid_str] = card_choice
        await db.update_game_session_state(conn, session_id, state)
        
        # Check if everyone has chosen
        all_chosen = len(state["choices"]) == len(state["players"])
        
    await update.message.reply_text(f"✅ {player_data['name']} telah memilih kartu.")
    
    if all_chosen:
        # Cancel timeout job
        jobs = context.job_queue.get_jobs_by_name(f"tujuh_pusaka_timeout_{session['chat_id']}")
        for j in jobs: j.schedule_removal()
        
        await resolve_round(context, db, conn, session["chat_id"], session_id)

async def job_timeout_round(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    round_num = job.data["round"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session or session["id"] != session_id: return
    
    state = json.loads(session["state_json"])
    if state["phase"] != PHASE_PLAYING or state["round"] != round_num: return
    
    await resolve_round(context, db, conn, chat_id, session_id)

def calculate_duel(p_card_id, b_card_id, p_penalty, b_penalty):
    # Base strengths
    p_str = CARDS[p_card_id]["base_str"] - p_penalty
    b_str = CARDS[b_card_id]["base_str"] - b_penalty
    
    if p_card_id == "pusaka" or b_card_id == "pusaka":
        if p_card_id == "pusaka" and b_card_id == "pusaka":
            return "draw", 0, 0, ""
            
    # Calculate effective strengths
    def get_effective(c_id, opp_id, current_str, opp_current_str):
        bonus = 0
        cancel_opp_bonus = False
        
        c_type = CARDS[c_id]["type"]
        opp_type = CARDS[opp_id]["type"]
        
        if c_id == "dika" and opp_type == "wakil_rektor":
            bonus = 15
        elif c_id == "nivia" and current_str < opp_current_str:
            bonus = 20
            cancel_opp_bonus = True
        elif c_id == "nuansa" and opp_type == "sekretaris":
            bonus = 20
        elif c_id == "dyah":
            cancel_opp_bonus = True
            
        return bonus, cancel_opp_bonus
        
    p_bonus = 0
    b_bonus = 0
    p_cancel_b = False
    b_cancel_p = False
    
    # Handle Leony
    p_virtual_id = p_card_id
    b_virtual_id = b_card_id
    if p_card_id == "leony": p_virtual_id = b_card_id
    if b_card_id == "leony": b_virtual_id = p_card_id

    # Normal effects
    p_bonus, p_cancel_b = get_effective(p_virtual_id, b_virtual_id, p_str, b_str)
    b_bonus, b_cancel_p = get_effective(b_virtual_id, p_virtual_id, b_str, p_str)
    
    # Apply cancellations
    if p_cancel_b: b_bonus = 0
    if b_cancel_p: p_bonus = 0
    
    final_p = p_str + p_bonus
    final_b = b_str + b_bonus
    
    # Check Pusaka
    reverse = False
    if p_card_id == "pusaka" or b_card_id == "pusaka":
        reverse = True
        
    # Winner determination
    if final_p > final_b:
        result = "player"
    elif final_b > final_p:
        result = "bot"
    else:
        result = "draw"
        
    if reverse and result != "draw":
        result = "bot" if result == "player" else "player"
        
    # Neil penalty
    p_next_pen = 0
    b_next_pen = 0
    if result == "bot" and p_card_id == "neil":
        b_next_pen = 20
    if result == "player" and b_card_id == "neil":
        p_next_pen = 20
        
    desc = f"{CARDS[p_card_id]['name']} ({final_p}) vs {CARDS[b_card_id]['name']} ({final_b})"
    if reverse: desc += " [REVERSED]"
    
    return result, p_next_pen, b_next_pen, desc

async def resolve_round(context: ContextTypes.DEFAULT_TYPE, db, conn, chat_id, session_id):
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["id"] != session_id: return
        state = json.loads(session["state_json"])
        if state["phase"] != PHASE_PLAYING: return
        
        round_num = state["round"]
        
        bot_available = state["bot_cards"]
        b_card_id = random.choice(bot_available)
        state["bot_cards"].remove(b_card_id)
        
        lines = [f"⚔️ <b>Hasil Ronde {round_num}</b>", f"🤖 Bot mengeluarkan: <b>{CARDS[b_card_id]['name']}</b>\n"]
        
        for uid_str, p_data in state["players"].items():
            if uid_str not in state["choices"]:
                if p_data["cards"]:
                    burned_card = random.choice(p_data["cards"])
                    p_data["cards"].remove(burned_card)
                    burned_name = CARDS[burned_card]["name"]
                    lines.append(f"❌ {p_data['name']} tidak memilih kartu (kalah) & kartu <b>{burned_name}</b> hangus dibakar waktu!")
                else:
                    lines.append(f"❌ {p_data['name']} tidak memilih kartu dan kalah.")
                p_data["next_round_penalty"] = 0
                p_data["bot_next_round_penalty"] = 0
                continue
                
            p_card_id = state["choices"][uid_str]
            p_data["cards"].remove(p_card_id)
            
            p_penalty = p_data["next_round_penalty"]
            b_penalty = p_data.get("bot_next_round_penalty", 0)
            
            res, p_next_pen, b_next_pen, desc = calculate_duel(p_card_id, b_card_id, p_penalty, b_penalty)
            
            p_data["bot_next_round_penalty"] = b_next_pen
            p_data["next_round_penalty"] = p_next_pen
            
            if res == "player":
                p_data["wins"] += 1
                lines.append(f"✅ {p_data['name']} <b>MENANG</b> | {desc}")
            elif res == "bot":
                lines.append(f"💀 {p_data['name']} <b>KALAH</b> | {desc}")
            else:
                lines.append(f"➖ {p_data['name']} <b>DRAW</b> | {desc}")
                
        state["choices"] = {}
        
        if round_num == 7:
            state["phase"] = PHASE_FINISHED
            await db.update_game_session_state(conn, session_id, state)
            
            lines.append("\n🏁 <b>PERMAINAN SELESAI!</b>\n<b>Papan Skor Akhir:</b>")
            sorted_players = sorted(state["players"].values(), key=lambda x: x["wins"], reverse=True)
            for p in sorted_players:
                lines.append(f"• {p['name']}: {p['wins']} Menang")
            
            await db.end_game_session(conn, session_id)
            await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")
        else:
            state["round"] += 1
            await db.update_game_session_state(conn, session_id, state)
            
            lines.append(f"\n🔜 <b>Ronde {state['round']}</b> dimulai! Ketik <code>/pusaka &lt;nama_kartu&gt;</code>.")
            await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")
            
            context.job_queue.run_once(
                job_timeout_round,
                120,
                chat_id=chat_id,
                name=f"tujuh_pusaka_timeout_{chat_id}",
                data={"session_id": session_id, "round": state["round"]}
            )
            context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 60, chat_id=chat_id, name=f"tpr_rem1_{chat_id}", data={"session_id": session_id, "round": state["round"], "text": f"⏳ <b>Ronde {state['round']}</b>: 1 menit lagi! Segera pilih kartu Anda."})
            context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 90, chat_id=chat_id, name=f"tpr_rem2_{chat_id}", data={"session_id": session_id, "round": state["round"], "text": f"⏳ <b>Ronde {state['round']}</b>: 30 detik lagi!"})
            context.job_queue.run_once(job_tujuh_pusaka_round_reminder, 105, chat_id=chat_id, name=f"tpr_rem3_{chat_id}", data={"session_id": session_id, "round": state["round"], "text": f"⏳ <b>Ronde {state['round']}</b>: 15 detik lagi!"})

async def status_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    if state["phase"] == PHASE_REGISTRATION:
        msg = f"🎮 <b>Tujuh Pusaka</b> (Registrasi)\n👥 {len(state['players'])} pemain terdaftar."
    else:
        msg = f"🎮 <b>Tujuh Pusaka</b> (Ronde {state['round']})\n⏳ Menunggu pemain memilih kartu..."
        uid_str = str(update.effective_user.id)
        if uid_str in state["players"]:
            p_data = state["players"][uid_str]
            sisa = ", ".join([c.title() for c in p_data["cards"]]) if p_data["cards"] else "Habis"
            msg += f"\n\n🃏 <b>Sisa Kartu {p_data['name']}:</b>\n{sisa}"
            
    await update.message.reply_text(msg, parse_mode="HTML")

async def berhenti_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "tujuh_pusaka":
            await update.message.reply_text("Tidak ada sesi Tujuh Pusaka yang aktif.")
            return

    jobs = context.job_queue.get_jobs_by_name(f"tujuh_pusaka_timeout_{chat_id}")
    for job in jobs: job.schedule_removal()
        
    await db.end_game_session(conn, session["id"])
    await update.message.reply_text("⏹ Game Tujuh Pusaka dihentikan secara paksa.")

async def hasil_tujuh_pusaka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    if "players" not in state: return
    
    lines = ["📜 <b>Hasil Terakhir Tujuh Pusaka</b>"]
    sorted_players = sorted(state["players"].values(), key=lambda x: x["wins"], reverse=True)
    for p in sorted_players:
        lines.append(f"• {p['name']}: {p['wins']} Menang")
        
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
