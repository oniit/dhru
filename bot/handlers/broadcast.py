import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter

from bot.handlers.common import user_row

def _conn(context): return context.application.bot_data["conn"]
def _db(context): return context.application.bot_data["db"]

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message: return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in ("owner", "admin"):
        await update.message.reply_text("Tidak diizinkan.")
        return
        
    parts = (update.message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Gunakan: /broadcast &lt;all|nonpublic|role_name&gt; &lt;pesan&gt;\nContoh: /broadcast student halo semua!")
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
        
    job_id = await db.add_broadcast_job(conn, message, [r["telegram_id"] for r in rows], uid)
    await update.message.reply_text(f"✅ Memulai broadcast ke {len(rows)} user (Job ID: {job_id}).\nSistem akan mengirimkan pesan di *background* untuk menghindari spam limit. Anda akan menerima notifikasi jika proses telah selesai.", parse_mode="Markdown")
