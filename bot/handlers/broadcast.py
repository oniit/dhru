import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.common import user_row

def _conn(context): return context.application.bot_data["conn"]
def _db(context): return context.application.bot_data["db"]

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message: return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in ("owner", "admin", "co_founder"):
        await update.message.reply_text("Tidak diizinkan.")
        return
        
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Gunakan: /broadcast <all|nonpublic|role_name> <pesan>\nContoh: /broadcast student halo semua!")
        return
        
    target = parts[1].lower()
    message = parts[2]
    
    if target == "all":
        cur = await conn.execute("SELECT telegram_id FROM users")
    elif target == "nonpublic":
        cur = await conn.execute("SELECT telegram_id FROM users WHERE role != 'public'")
    else:
        cur = await conn.execute("SELECT telegram_id FROM users WHERE role = ?", (target,))
        
    rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Tidak ada user yang sesuai kriteria.")
        return
        
    await update.message.reply_text(f"Memulai broadcast ke {len(rows)} user...")
    
    context.application.create_task(
        run_broadcast(context, [r["telegram_id"] for r in rows], message, uid)
    )

async def run_broadcast(context: ContextTypes.DEFAULT_TYPE, uids: list[int], message: str, reporter_id: int):
    success = 0
    fail = 0
    for i, user_id in enumerate(uids):
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success += 1
        except Exception:
            fail += 1
        if i % 20 == 0:
            await asyncio.sleep(1)
            
    await context.bot.send_message(chat_id=reporter_id, text=f"Broadcast selesai:\nBerhasil: {success}\nGagal: {fail}")
