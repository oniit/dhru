import json
import re
from telegram import Update
from telegram.ext import ContextTypes

# Command: /atur kata_rahasia <nama_setting> <kata1>, <kata2>, ...
async def atur_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, setting_name: str, args_text: str):
    if not args_text:
        await update.message.reply_text("Penggunaan: /atur kata_rahasia <nama_setting> <kata1>, <kata2>, ...")
        return

    words = [w.strip().lower() for w in args_text.split(",") if w.strip()]
    if not words:
        await update.message.reply_text("Tidak ada kata rahasia yang valid ditemukan.")
        return

    data = {"words": words}
    await db.upsert_game_setting(conn, "kata_rahasia", setting_name, data)
    
    await update.message.reply_text(f"✅ Setting '{setting_name}' untuk Kata Rahasia berhasil disimpan dengan {len(words)} kata.")

# Command: /bermain kata_rahasia <nama_setting>
async def mulai_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, setting_name: str):
    chat_id = update.effective_chat.id
    
    # Check if there is an active session
    active = await db.get_active_game_session(conn, chat_id)
    if active:
        await update.message.reply_text(f"⚠️ Masih ada game {active['game_name']} yang aktif di grup ini. Hentikan dulu dengan /berhenti {active['game_name']}.")
        return

    setting = await db.get_game_setting(conn, "kata_rahasia", setting_name)
    if not setting:
        await update.message.reply_text(f"❌ Setting '{setting_name}' tidak ditemukan untuk game Kata Rahasia.")
        return
        
    active_words = setting.get("words", [])
    if not active_words:
        await update.message.reply_text("❌ Setting ini tidak memiliki daftar kata.")
        return
        
    initial_state = {
        "active_words": active_words,
        "scores": {}, # format: {"telegram_id": {"name": "User Name", "score": 10}}
        "total_words": len(active_words),
        "started_by": update.effective_user.id
    }
    
    await db.start_game_session(conn, chat_id, "kata_rahasia", setting_name, initial_state)
    
    await update.message.reply_text(
        f"🎮 **Kata Rahasia** dimulai!\n📍 Setting: {setting_name}\n🔐 Jumlah kata: {len(active_words)}\n\n"
        "Bermainlah secara natural, sebutkan kata-kata rahasia yang tepat untuk mendapatkan poin!",
        parse_mode="Markdown"
    )

# Dipanggil oleh router jika grup ini memiliki game kata_rahasia yang aktif
async def proses_pesan_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    text = update.message.text or update.message.caption or ""
    text_lower = text.lower()
    
    state = json.loads(session["state_json"])
    active_words = state.get("active_words", [])
    
    if not active_words:
        return
        
    found_words = []
    
    # Check regex bounds for each active word to prevent partial match (e.g. lari vs pelarian)
    for word in list(active_words):
        # Escape word just in case it contains regex special chars
        escaped_word = re.escape(word)
        pattern = r"\b" + escaped_word + r"\b"
        if re.search(pattern, text_lower):
            found_words.append(word)
            active_words.remove(word)
            
    if found_words:
        points = len(found_words)
        user = update.effective_user
        uid_str = str(user.id)
        
        # Update score
        scores = state.setdefault("scores", {})
        if uid_str not in scores:
            scores[uid_str] = {
                "name": user.first_name or user.username or str(user.id),
                "score": 0
            }
        scores[uid_str]["score"] += points
        
        # Update state to DB
        await db.update_game_session_state(conn, session["id"], state)
        
        await update.message.reply_text(
            f"🎯 Benar! +{points} poin untuk {user.first_name}!",
            reply_to_message_id=update.message.message_id
        )
        
        if not active_words:
            # End game auto
            await update.message.reply_text("🎉 Semua kata rahasia telah ditebak!")
            await berhenti_kata_rahasia(update, context, db, conn, session)


async def status_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    active_words = state.get("active_words", [])
    total_words = state.get("total_words", 0)
    scores = state.get("scores", {})
    
    players_count = len(scores)
    
    players_count = len(scores)
    
    status_text = (
        f"🎮 **Status Kata Rahasia**\n"
        f"📍 Setting: {session['setting_name']}\n"
        f"🔐 Kata tersisa: {len(active_words)}/{total_words}"
    )
    
    if scores:
        status_text += "\n\n📊 **Skor Sementara:**\n"
        sorted_scores = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        for i, s in enumerate(sorted_scores[:10]):
            status_text += f"{i+1}. {s['name']} — {s['score']} poin\n"
            
    await update.message.reply_text(
        status_text,
        parse_mode="Markdown"
    )

async def berhenti_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict = None):
    chat_id = update.effective_chat.id
    if not session:
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "kata_rahasia":
            await update.message.reply_text("Tidak ada sesi Kata Rahasia yang aktif di grup ini.")
            return

    await db.end_game_session(conn, session["id"])
    
    state = json.loads(session["state_json"])
    scores = state.get("scores", {})
    
    if not scores:
        await update.message.reply_text("🎉 **KATA RAHASIA SELESAI!**\n\nBelum ada poin yang terkumpul.", parse_mode="Markdown")
        return
        
    sorted_scores = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    
    lines = ["🎉 **KATA RAHASIA SELESAI!**\n", "🏆 **HASIL AKHIR**"]
    medals = ["🥇", "🥈", "🥉"]
    
    for i, s in enumerate(sorted_scores):
        medal = medals[i] if i < len(medals) else "▫️"
        lines.append(f"{medal} {s['name']} — {s['score']} poin")
        
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error sending final score for kata_rahasia: {e}")

async def hasil_kata_rahasia(update: Update, context: ContextTypes.DEFAULT_TYPE, db, conn, session: dict):
    state = json.loads(session["state_json"])
    scores = state.get("scores", {})
    
    if not scores:
        await update.message.reply_text("📉 **HASIL KATA RAHASIA TERAKHIR**\n\nBelum ada poin yang terkumpul pada sesi tersebut.", parse_mode="Markdown")
        return
        
    sorted_scores = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    
    lines = ["📜 **HASIL KATA RAHASIA TERAKHIR**\n"]
    medals = ["🥇", "🥈", "🥉"]
    
    for i, s in enumerate(sorted_scores):
        medal = medals[i] if i < len(medals) else "▫️"
        lines.append(f"{medal} {s['name']} — {s['score']} poin")
        
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown"
    )
