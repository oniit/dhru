import json
import random
import re
from telegram import Update
from telegram.ext import ContextTypes

# Mapping digit ke huruf
DIGIT_TO_WORD = {
    '0': 'nol',
    '1': 'satu',
    '2': 'dua',
    '3': 'tiga',
    '4': 'empat',
    '5': 'lima',
    '6': 'enam',
    '7': 'tujuh',
    '8': 'delapan',
    '9': 'sembilan'
}

def clean_text(text: str) -> str:
    """Membersihkan teks dari spasi berlebih untuk memudahkan perbandingan."""
    return re.sub(r'\s+', ' ', text.strip().lower())

# Command: /bermain ketik_angka
async def mulai_ketik_angka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn):
    chat_id = update.effective_chat.id
    
    # Check if there is an active session
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini. Hentikan dulu dengan /berhenti {active['game_name']}.")
        return

    # Generate random number
    num = random.randint(100, 9999999)
    num_str = str(num)
    
    # Generate words
    words = [DIGIT_TO_WORD[d] for d in num_str]
    words_str = " ".join(words)
    
    # Randomly select mode
    # mode_type: 1 = Angka ke Huruf, 2 = Huruf ke Angka
    mode_type = random.choice([1, 2])
    
    if mode_type == 1:
        question = num_str
        expected_answer = clean_text(words_str)
        mode_name = "Angka ke Huruf"
        instruction = "Ketik ejaan dari angka di atas dengan cepat!"
    else:
        question = words_str
        expected_answer = num_str
        mode_name = "Huruf ke Angka"
        instruction = "Ketik angka dari ejaan di atas dengan cepat!"

    initial_state = {
        "question": question,
        "expected_answer": expected_answer,
        "mode_name": mode_name,
        "mode_type": mode_type,
        "winners": [], # Format: [{"id": 123, "name": "Budi", "points": 3}]
        "started_by": update.effective_user.id
    }
    
    await db.start_game_session(conn, chat_id, "ketik_angka", "default", initial_state)
    
    await update.message.reply_text(
        f"🎮 *Ketik Angka* dimulai!\n"
        f"📍 Mode: {mode_name}\n\n"
        f"📝 Soal:\n*{question}*\n\n"
        f"_{instruction}_\n"
        f"(Dicari 3 pemenang tercepat!)",
        parse_mode="Markdown"
    )

async def proses_pesan_ketik_angka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    text = update.message.text or update.message.caption or ""
    text_clean = clean_text(text)
    
    state = json.loads(session["state_json"])
    expected_answer = state.get("expected_answer", "")
    winners = state.get("winners", [])
    
    if len(winners) >= 3:
        return # Should not happen if game is ended properly, but just in case
        
    # Periksa apakah user sudah menang
    uid_str = str(update.effective_user.id)
    if any(str(w["id"]) == uid_str for w in winners):
        return # User ini sudah menjawab benar sebelumnya
        
    if text_clean == expected_answer:
        # User menjawab dengan benar
        rank = len(winners) + 1
        points = 4 - rank # Peringkat 1 = 3 poin, 2 = 2 poin, 3 = 1 poin
        
        user = update.effective_user
        name = user.first_name or user.username or uid_str
        
        winner_data = {
            "id": uid_str,
            "name": name,
            "points": points
        }
        winners.append(winner_data)
        
        # Update state
        state["winners"] = winners
        
        # Update state to DB
        await db.update_game_session_state(conn, session["id"], state)
        
        # Convert session to mutable dict
        if not isinstance(session, dict):
            session = {k: session[k] for k in session.keys()}
        session["state_json"] = json.dumps(state)
        
        await update.message.reply_text(
            f"🎯 Benar! {name} adalah tercepat ke-{rank} (+{points} poin)!",
            reply_to_message_id=update.message.message_id
        )
        
        if len(winners) >= 3:
            # End game auto
            await update.message.reply_text("🎉 Sudah ada 3 pemenang tercepat!")
            await berhenti_ketik_angka(update, context, db, conn, session)

async def status_ketik_angka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    question = state.get("question", "")
    mode_name = state.get("mode_name", "")
    winners = state.get("winners", [])
    
    status_text = (
        f"🎮 *Status Ketik Angka*\n"
        f"📍 Mode: {mode_name}\n\n"
        f"📝 Soal:\n*{question}*\n"
    )
    
    if winners:
        status_text += "\n📊 *Telah Menjawab:*\n"
        for i, w in enumerate(winners):
            status_text += f"{i+1}. {w['name']} — +{w['points']} poin\n"
            
    status_text += f"\nMasih mencari {3 - len(winners)} pemenang lagi!"
            
    await update.message.reply_text(
        status_text,
        parse_mode="Markdown"
    )

async def berhenti_ketik_angka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "ketik_angka":
            await update.message.reply_text("Tidak ada sesi Ketik Angka yang aktif di grup ini.")
            return

    await db.end_game_session(conn, session["id"])
    
    state = json.loads(session["state_json"])
    winners = state.get("winners", [])
    expected_answer = state.get("expected_answer", "")
    
    if not winners:
        await update.message.reply_text(f"🎉 *KETIK ANGKA SELESAI!*\n\nJawaban yang benar adalah: `{expected_answer}`\n\nBelum ada yang berhasil menjawab dengan benar.", parse_mode="Markdown")
        return
        
    lines = [f"🎉 *KETIK ANGKA SELESAI!*\n\nJawaban: `{expected_answer}`\n", "🏆 *PEMENANG*"]
    medals = ["🥇", "🥈", "🥉"]
    
    for i, w in enumerate(winners):
        medal = medals[i] if i < len(medals) else "▫️"
        lines.append(f"{medal} {w['name']} — {w['points']} poin")
        
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error sending final score for ketik_angka: {e}")

async def hasil_ketik_angka(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    winners = state.get("winners", [])
    expected_answer = state.get("expected_answer", "")
    
    if not winners:
        await update.message.reply_text("📉 *HASIL KETIK ANGKA TERAKHIR*\n\nBelum ada yang berhasil menjawab pada sesi tersebut.", parse_mode="Markdown")
        return
        
    lines = [f"📜 *HASIL KETIK ANGKA TERAKHIR*\n\nJawaban: `{expected_answer}`\n"]
    medals = ["🥇", "🥈", "🥉"]
    
    for i, w in enumerate(winners):
        medal = medals[i] if i < len(medals) else "▫️"
        lines.append(f"{medal} {w['name']} — {w['points']} poin")
        
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown"
    )
