import json
import random
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

# PHASE CONSTANTS
PHASE_DEPOSIT = "deposit"
PHASE_GUESS = "guess"
PHASE_FINISHED = "finished"

# Command: /bermain kantong_rempah <menit_setor> <menit_tebak>
async def mulai_kantong_rempah(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, args_text: str):
    chat_id = update.effective_chat.id
    
    # Parse times
    menit_setor = 2
    menit_tebak = 3
    
    if args_text:
        parts = args_text.split()
        if len(parts) == 1:
            try:
                val = int(parts[0])
                menit_setor = val
                menit_tebak = val
            except ValueError:
                pass
        elif len(parts) >= 2:
            try:
                menit_setor = int(parts[0])
                menit_tebak = int(parts[1])
            except ValueError:
                pass
                
    if menit_setor < 1: menit_setor = 1
    if menit_tebak < 1: menit_tebak = 1
    
    # Check if there is an active session
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini. Hentikan dulu dengan /berhenti {active['game_name']}.")
        return

    # Inisialisasi state
    initial_state = {
        "phase": PHASE_DEPOSIT,
        "started_by": update.effective_user.id,
        "deposits": {}, # format: {"telegram_id": {"name": "User Name", "amount": 5}}
        "guesses": {}, # format: {"telegram_id": {"name": "User Name", "guess": 15}}
        "bot_deposit": 0,
        "bot_guess": 0,
        "total_deposit": 0,
        "menit_setor": menit_setor,
        "menit_tebak": menit_tebak,
        "scores": {}
    }
    
    # The setting_name is unused but required by db schema
    await db.start_game_session(conn, chat_id, "kantong_rempah", "default", initial_state)
    
    # Retrieve the inserted session to pass its ID to the job
    session = await db.get_active_game_session(conn, chat_id)
    if not session:
        return
        
    bot_username = context.bot.username
    url = f"https://t.me/{bot_username}?start=rempah_{chat_id}"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Setor Rempah (PC)", url=url)]
    ])
    
    await update.message.reply_text(
        f"🎮 **Kantong Rempah** dimulai!\n\n"
        f"Tahap 1: **Setor Rempah**\n"
        f"Silakan setor jumlah rempah Anda (0-10) melalui PC bot dengan mengeklik tombol di bawah.\n\n"
        f"⏱ Waktu setor: **{menit_setor} menit**",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    
    # Jadwalkan perpindahan ke Guess Phase
    context.job_queue.run_once(
        job_end_deposit_phase,
        menit_setor * 60,
        chat_id=chat_id,
        name=f"rempah_dep_{chat_id}",
        data={"session_id": session["id"]}
    )


async def job_end_deposit_phase(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session or session["id"] != session_id or session["game_name"] != "kantong_rempah":
        return # Game dihentikan atau tidak valid
        
    state = json.loads(session["state_json"])
    if state["phase"] != PHASE_DEPOSIT:
        return
        
    # Acak setoran bot (0-10)
    bot_deposit = random.randint(0, 10)
    state["bot_deposit"] = bot_deposit
    
    # Hitung total deposit
    total_deposit = bot_deposit
    players_count = len(state.get("deposits", {}))
    for uid_str, data in state.get("deposits", {}).items():
        total_deposit += data["amount"]
        
    state["total_deposit"] = total_deposit
    
    # Ubah phase
    state["phase"] = PHASE_GUESS
    await db.update_game_session_state(conn, session_id, state)
    
    menit_tebak = state.get("menit_tebak", 3)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ **Waktu Setor Habis!**\n\n"
             f"Rempah berhasil dikumpulkan oleh **{players_count} pemain** + **1 bot**.\n"
             f"Sekarang tebak total seluruh rempah yang terkumpul!\n\n"
             f"Ketik `/tebak <angka>` di grup ini (contoh: `/tebak 15`).\n\n"
             f"⏱ Waktu tebak: **{menit_tebak} menit**",
        parse_mode="Markdown"
    )
    
    context.job_queue.run_once(
        job_end_guess_phase,
        menit_tebak * 60,
        chat_id=chat_id,
        name=f"rempah_guess_{chat_id}",
        data={"session_id": session_id}
    )

async def job_end_guess_phase(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    session_id = job.data["session_id"]
    
    db = context.application.bot_data["db"]
    conn = context.application.bot_data["conn"]
    
    session = await db.get_active_game_session(conn, chat_id)
    if not session or session["id"] != session_id or session["game_name"] != "kantong_rempah":
        return
        
    state = json.loads(session["state_json"])
    if state["phase"] != PHASE_GUESS:
        return
        
    # Akhiri game
    state["phase"] = PHASE_FINISHED
    await db.update_game_session_state(conn, session_id, state)
    await db.end_game_session(conn, session_id)
    
    total_deposit = state["total_deposit"]
    bot_deposit = state["bot_deposit"]
    guesses = state.get("guesses", {})
    deposits = state.get("deposits", {})
    
    # Bot makes a random guess between 0 and (players_count + 1) * 10
    max_possible_total = (len(deposits) + 1) * 10
    bot_guess = random.randint(0, max_possible_total)
    
    lines = [
        "🎉 **WAKTU HABIS! HASIL KANTONG REMPAH**\n",
        f"Setoran Bot: **{bot_deposit}**",
        f"Total Rempah Sebenarnya: **{total_deposit}**\n",
    ]
    
    if not guesses:
        lines.append("😅 Tidak ada yang menebak di ronde ini.")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
        return
        
    # Hitung selisih
    results = []
    for uid_str, data in guesses.items():
        diff = abs(data["guess"] - total_deposit)
        results.append({
            "uid": uid_str,
            "name": data["name"],
            "guess": data["guess"],
            "diff": diff
        })
        
    # Tambahkan bot ke hasil
    bot_diff = abs(bot_guess - total_deposit)
    results.append({
        "uid": "bot",
        "name": "🤖 Komputer",
        "guess": bot_guess,
        "diff": bot_diff
    })
    
    # Urutkan berdasarkan selisih terkecil
    results.sort(key=lambda x: x["diff"])
    
    best_diff = results[0]["diff"]
    winners = [r for r in results if r["diff"] == best_diff]
    
    lines.append("🏆 **Peringkat Tebakan:**")
    for i, r in enumerate(results[:10]):
        medal = "🥇" if r["diff"] == best_diff else "▫️"
        lines.append(f"{medal} {r['name']} — Tebak: {r['guess']} (Selisih {r['diff']})")
        
    lines.append("\n🌟 **Pemenang:**")
    winner_names = [w["name"] for w in winners]
    lines.append(", ".join(winner_names))
    if best_diff == 0:
        lines.append("_(Tebakan Tepat Sasaran! 🎯)_")
        
    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

import asyncio

async def proses_tebakan_grup(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict, text: str):
    # Dipanggil oleh games.py jika ada pesan berawalan /tebak
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return
        
    try:
        guess_val = int(parts[1])
    except ValueError:
        return
        
    session_id = session["id"]
    lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
    
    async with lock:
        # Re-fetch session to get the latest state inside the lock
        current_session = await db.get_active_game_session(conn, session["chat_id"])
        if not current_session or current_session["id"] != session_id:
            return
            
        state = json.loads(current_session["state_json"])
        if state["phase"] != PHASE_GUESS:
            return # Abaikan jika bukan fase tebak
            
        user = update.effective_user
        uid_str = str(user.id)
        
        guesses = state.setdefault("guesses", {})
        
        # Perbolehkan update tebakan
        guesses[uid_str] = {
            "name": user.first_name or user.username or str(user.id),
            "guess": guess_val
        }
        
        await db.update_game_session_state(conn, session_id, state)

async def status_kantong_rempah(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    phase = state["phase"]
    
    if phase == PHASE_DEPOSIT:
        players = len(state.get("deposits", {}))
        msg = f"🎮 **Kantong Rempah** (Fase Setor)\n👥 Menunggu setoran... ({players} pemain telah menyetor)"
    elif phase == PHASE_GUESS:
        players = len(state.get("guesses", {}))
        msg = f"🎮 **Kantong Rempah** (Fase Tebak)\n🗣 Menunggu tebakan... ({players} pemain telah menebak)"
    else:
        msg = "🎮 **Kantong Rempah** (Selesai)"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def berhenti_kantong_rempah(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "kantong_rempah":
            await update.message.reply_text("Tidak ada sesi Kantong Rempah yang aktif di grup ini.")
            return

    # Cancel jobs
    current_jobs = context.job_queue.get_jobs_by_name(f"rempah_dep_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    current_jobs = context.job_queue.get_jobs_by_name(f"rempah_guess_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
        
    await db.end_game_session(conn, session["id"])
    await update.message.reply_text("⏹ Game Kantong Rempah telah dihentikan secara paksa.")

async def hasil_kantong_rempah(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    total_deposit = state.get("total_deposit", 0)
    bot_deposit = state.get("bot_deposit", 0)
    
    await update.message.reply_text(f"📜 **Hasil Terakhir Kantong Rempah**\nTotal deposit: {total_deposit}\nDeposit Bot: {bot_deposit}", parse_mode="Markdown")
