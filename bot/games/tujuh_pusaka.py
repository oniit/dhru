import json
import random
import asyncio
import html
from telegram import Update
from telegram.ext import ContextTypes
from bot.settings import is_admin_elevated

# PHASE CONSTANTS
PHASE_REGISTRATION = "registration"
PHASE_PLAYING = "playing"
PHASE_FINISHED = "finished"

# ==============================================================================
# DAFTAR NAMA KARTU TUJUH PUSAKA
# Ubah nama kartu di sini kapan saja (misal jika ada pergantian karakter/staf).
# Key: jabatan/slot kartu (rektor, warek1, warek2, sekre1, sekre2, sekre3, pusaka).
# Value: nama karakter/staf yang akan tampil di game.
# ==============================================================================
NAMA_KARTU = {
    "rektor": "Dika",          # Rektor (Str 90) - +15 Str vs Warek 1 & Warek 2
    "warek1": "Nuansa",         # Wakil Rektor 1 (Str 75) - +20 Str vs Str lebih tinggi & batalkan bonus lawan
    "warek2": "Ivana",        # Wakil Rektor 2 (Str 75) - +20 Str vs Sekretaris
    "sekre1": "Dyah",        # Sekretaris 1 (Str 60) - Menyalin Power lawan
    "sekre2": "Sachi",          # Sekretaris 2 (Str 60) - Membatalkan seluruh bonus lawan
    "sekre3": "Prati",          # Sekretaris 3 (Str 60) - Jika kalah, lawan -20 Str di ronde berikutnya
    "pusaka": "Kartu Pusaka",  # Pusaka (Str -) - Membalikkan hasil duel (Menang <-> Kalah)
}

CARDS = {
    "rektor": {"name": NAMA_KARTU["rektor"], "base_str": 90, "type": "rektor"},
    "warek1": {"name": NAMA_KARTU["warek1"], "base_str": 75, "type": "wakil_rektor"},
    "warek2": {"name": NAMA_KARTU["warek2"], "base_str": 75, "type": "wakil_rektor"},
    "sekre1": {"name": NAMA_KARTU["sekre1"], "base_str": 60, "type": "sekretaris"},
    "sekre2": {"name": NAMA_KARTU["sekre2"], "base_str": 60, "type": "sekretaris"},
    "sekre3": {"name": NAMA_KARTU["sekre3"], "base_str": 60, "type": "sekretaris"},
    "pusaka": {"name": NAMA_KARTU["pusaka"], "base_str": 0, "type": "pusaka"},
}

LEGACY_KEYS = {
    "dika": "rektor",
    "nivia": "warek1",
    "nuansa": "warek2",
    "leonie": "sekre1",
    "dyah": "sekre2",
    "neil": "sekre3",
    "pusaka": "pusaka",
}

def get_card_info() -> str:
    n_rek = CARDS["rektor"]["name"]
    n_w1 = CARDS["warek1"]["name"]
    n_w2 = CARDS["warek2"]["name"]
    n_s1 = CARDS["sekre1"]["name"]
    n_s2 = CARDS["sekre2"]["name"]
    n_s3 = CARDS["sekre3"]["name"]
    n_pus = CARDS["pusaka"]["name"]
    return (
        f"📜 <b>Tujuh Pusaka</b>\n"
        f"1. <b>{n_rek}</b> (Str 90) - +15 Str vs {n_w1}/{n_w2}.\n"
        f"2. <b>{n_w1}</b> (Str 75) - +20 Str vs kartu Str lebih tinggi, dan target kehilangan bonus Str-nya.\n"
        f"3. <b>{n_w2}</b> (Str 75) - +20 Str vs {n_s1}/{n_s2}/{n_s3}.\n"
        f"4. <b>{n_s1}</b> (Str 60) - Menyalin Power lawan, Str tetap 60.\n"
        f"5. <b>{n_s2}</b> (Str 60) - Membatalkan seluruh bonus Str lawan.\n"
        f"6. <b>{n_s3}</b> (Str 60) - Jika kalah, Str lawan -20 di ronde berikutnya.\n"
        f"7. <b>{n_pus}</b> (Str -) - Membalikkan hasil duel (Menang jadi Kalah, Kalah jadi Menang). {n_pus} vs {n_pus} = Draw."
    )

CARD_INFO = get_card_info()


def resolve_card_id(card_choice: str) -> str | None:
    """Mencocokkan input pemain dengan ID kartu secara fleksibel & case-insensitive."""
    if not card_choice:
        return None
    choice = card_choice.strip().lower()
    clean_choice = choice.replace(" ", "")

    # 1. Cocokkan langsung dengan ID role internal (contoh: "rektor", "warek1", "sekre1", "pusaka")
    if clean_choice in CARDS:
        return clean_choice

    # 2. Cocokkan dengan key nama legacy (contoh: "dika", "nivia", "leonie")
    if clean_choice in LEGACY_KEYS:
        return LEGACY_KEYS[clean_choice]

    # 3. Cocokkan dengan nama tampilan yang sedang aktif (contoh: "Dika", "Kartu Pusaka")
    for cid, info in CARDS.items():
        if choice == info["name"].strip().lower():
            return cid

    # 4. Cocokkan jika nama memakai awalan 'Kartu ' (contoh: ketik "pusaka" untuk "Kartu Pusaka")
    for cid, info in CARDS.items():
        clean_name = info["name"].strip().lower()
        if clean_name.startswith("kartu ") and choice == clean_name[6:].strip():
            return cid

    # 5. Fallback urutan nomor 1-7
    card_keys = list(CARDS.keys())
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(card_keys):
            return card_keys[idx]

    return None

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
            await db.end_game_session(conn, session_id)
            context.bot_data.setdefault("active_game_chats", set()).discard(chat_id)
            return
            
        state["phase"] = PHASE_PLAYING
        state["round"] = 1
        
        await db.update_game_session_state(conn, session_id, state)
        
    ex_card = CARDS["rektor"]["name"].lower()
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⚔️ <b>Permainan Dimulai Secara Otomatis!</b>\n\n"
            f"<b>Ronde 1</b>\n"
            f"Silakan setiap pemain memilih 1 kartu dengan mengetik:\n"
            f"<code>/pusaka &lt;nama_kartu&gt;</code> (Contoh: <code>/pusaka {ex_card}</code>)\n\n"
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
    
    ex_card = CARDS["rektor"]["name"].lower()
    await update.message.reply_text(
        f"⚔️ <b>Permainan Dimulai!</b>\n\n"
        f"<b>Ronde 1</b>\n"
        f"Silakan setiap pemain memilih 1 kartu dengan mengetik:\n"
        f"<code>/pusaka &lt;nama_kartu&gt;</code> (Contoh: <code>/pusaka {ex_card}</code>)\n\n"
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
        uid = update.effective_user.id
        if uid == state.get("started_by") or is_admin_elevated(uid):
            await paksa_mulai_tujuh_pusaka(update, context, db, conn, session)
        return
        
    if cmd == "/pusaka" or cmd.startswith("/pusaka@"):
        if len(parts) < 2: return
        card_choice = " ".join(parts[1:]).strip()
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
            
        card_id = resolve_card_id(card_choice)
        if not card_id or card_id not in CARDS:
            valid_list = ", ".join(info["name"] for info in CARDS.values())
            await update.message.reply_text(
                f"⚠️ <b>{html.escape(card_choice)}</b> bukan kartu yang valid.\n\n"
                f"Pilihan kartu: {html.escape(valid_list)}",
                parse_mode="HTML"
            )
            return
            
        player_data = state["players"][uid_str]
        if card_id not in player_data["cards"]:
            chosen_name = CARDS[card_id]["name"]
            await update.message.reply_text(
                f"⚠️ {html.escape(player_data['name'])}, Anda sudah menggunakan kartu <b>{html.escape(chosen_name)}</b>!",
                parse_mode="HTML"
            )
            return
            
        if uid_str in state["choices"]:
            await update.message.reply_text(
                f"⚠️ {html.escape(player_data['name'])}, Anda sudah memilih kartu ronde ini!",
                parse_mode="HTML"
            )
            return
            
        state["choices"][uid_str] = card_id
        await db.update_game_session_state(conn, session_id, state)
        
        # Check if everyone has chosen
        all_chosen = len(state["choices"]) == len(state["players"])
        round_for_resolve = state["round"]
        
    await update.message.reply_text(f"✅ {player_data['name']} telah memilih kartu.")
    
    if all_chosen:
        # Cancel timeout job
        jobs = context.job_queue.get_jobs_by_name(f"tujuh_pusaka_timeout_{session['chat_id']}")
        for j in jobs: j.schedule_removal()
        
        await resolve_round(context, db, conn, session["chat_id"], session_id, expected_round=round_for_resolve)

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
    
    await resolve_round(context, db, conn, chat_id, session_id, expected_round=round_num)

def calculate_duel(p_card_id, b_card_id, p_penalty, b_penalty):
    p_card_id = LEGACY_KEYS.get(p_card_id, p_card_id)
    b_card_id = LEGACY_KEYS.get(b_card_id, b_card_id)
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
        
        if (c_id == "rektor" or c_id == "dika") and opp_type == "wakil_rektor":
            bonus = 15
        elif (c_id == "warek1" or c_id == "nivia") and current_str < opp_current_str:
            bonus = 20
            cancel_opp_bonus = True
        elif (c_id == "warek2" or c_id == "nuansa") and opp_type == "sekretaris":
            bonus = 20
        elif c_id in ("sekre2", "dyah"):
            cancel_opp_bonus = True
            
        return bonus, cancel_opp_bonus
        
    p_bonus = 0
    b_bonus = 0
    p_cancel_b = False
    b_cancel_p = False
    
    # Handle Leonie / Sekre 1
    p_virtual_id = p_card_id
    b_virtual_id = b_card_id
    if p_card_id in ("sekre1", "leonie"): p_virtual_id = b_card_id
    if b_card_id in ("sekre1", "leonie"): b_virtual_id = p_card_id

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
        
    # Neil penalty / Sekre 3
    p_next_pen = 0
    b_next_pen = 0
    if result == "bot" and p_card_id in ("sekre3", "neil"):
        b_next_pen = 20
    if result == "player" and b_card_id in ("sekre3", "neil"):
        p_next_pen = 20
        
    desc = f"{CARDS[p_card_id]['name']} ({final_p}) vs {CARDS[b_card_id]['name']} ({final_b})"
    if reverse: desc += " [REVERSED]"
    
    return result, p_next_pen, b_next_pen, desc

async def resolve_round(context: ContextTypes.DEFAULT_TYPE, db, conn, chat_id, session_id, expected_round: int | None = None):
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["id"] != session_id: return
        state = json.loads(session["state_json"])
        if state["phase"] != PHASE_PLAYING: return
        
        round_num = state["round"]
        if expected_round is not None and round_num != expected_round:
            return
        
        bot_available = state["bot_cards"]
        b_card_id = random.choice(bot_available)
        state["bot_cards"].remove(b_card_id)
        
        lines = [f"⚔️ <b>Hasil Ronde {round_num}</b>", f"🤖 Bot mengeluarkan: <b>{CARDS[b_card_id]['name']}</b>\n"]
        
        for uid_str, p_data in state["players"].items():
            p_name = html.escape(str(p_data.get("name") or "Pemain"))
            if uid_str not in state["choices"]:
                if p_data["cards"]:
                    burned_card = random.choice(p_data["cards"])
                    p_data["cards"].remove(burned_card)
                    burned_name = CARDS[burned_card]["name"]
                    lines.append(f"❌ {p_name} tidak memilih kartu (kalah) & kartu <b>{burned_name}</b> hangus dibakar waktu!")
                else:
                    lines.append(f"❌ {p_name} tidak memilih kartu dan kalah.")
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
                lines.append(f"✅ {p_name} <b>MENANG</b> | {desc}")
            elif res == "bot":
                lines.append(f"💀 {p_name} <b>KALAH</b> | {desc}")
            else:
                lines.append(f"➖ {p_name} <b>DRAW</b> | {desc}")
                
        state["choices"] = {}
        
        if round_num == 7:
            state["phase"] = PHASE_FINISHED
            await db.update_game_session_state(conn, session_id, state)
            
            lines.append("\n🏁 <b>PERMAINAN SELESAI!</b>\n<b>Papan Skor Akhir:</b>")
            sorted_players = sorted(state["players"].values(), key=lambda x: x["wins"], reverse=True)
            for p in sorted_players:
                p_esc = html.escape(str(p.get("name") or "Pemain"))
                lines.append(f"• {p_esc}: {p['wins']} Menang")
            
            await db.end_game_session(conn, session_id)
            context.bot_data.setdefault("active_game_chats", set()).discard(chat_id)
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
            sisa = ", ".join([CARDS.get(c, {}).get("name", c.title()) for c in p_data["cards"]]) if p_data["cards"] else "Habis"
            msg += f"\n\n🃏 <b>Sisa Kartu {html.escape(p_data['name'])}:</b>\n{html.escape(sisa)}"
            
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
