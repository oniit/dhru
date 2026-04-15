import json
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.common import user_row

def _conn(context): return context.application.bot_data["conn"]
def _db(context): return context.application.bot_data["db"]

async def check_admin(update, context):
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in ("owner", "admin", "co_founder"):
        await update.message.reply_text("Tidak diizinkan.")
        return False
    return True

async def cmd_addtrigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Gunakan: /addtrigger <keyword>")
        return
    keyword = parts[1].strip().lower()
    
    context.user_data["trigger_draft"] = {"keyword": keyword, "messages": []}
    await update.message.reply_text(f"Mulai membuat trigger untuk keyword: `{keyword}`\nSilakan kirim pesan balasan satu per satu. Jika sudah, ketik /selesai_trigger", parse_mode="Markdown")

async def cmd_selesai_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    draft = context.user_data.get("trigger_draft")
    if not draft:
        await update.message.reply_text("Tidak ada draft trigger aktif. Gunakan /addtrigger <keyword>.")
        return
    
    keyword = draft["keyword"]
    messages = draft["messages"]
    
    if not messages:
        await update.message.reply_text("Trigger dibatalkan karena tidak ada pesan.")
        context.user_data.pop("trigger_draft", None)
        return
        
    conn = _conn(context)
    actions_json = json.dumps(messages, ensure_ascii=False)
    await conn.execute("INSERT INTO triggers (keyword, actions_json, created_by) VALUES (?, ?, ?)", (keyword, actions_json, update.effective_user.id))
    await conn.commit()
    
    context.user_data.pop("trigger_draft", None)
    await update.message.reply_text(f"✅ Trigger untuk `{keyword}` berhasil disimpan dengan {len(messages)} pesan balasan.", parse_mode="Markdown")

async def cmd_listtrigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    conn = _conn(context)
    cur = await conn.execute("SELECT * FROM triggers ORDER BY id DESC")
    rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Belum ada trigger yang terdaftar.")
        return
    lines = ["**Daftar Trigger:**"]
    for r in rows:
        lines.append(f"ID {r['id']}: `{r['keyword']}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_deltrigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    parts = update.message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("Gunakan: /deltrigger <id>")
        return
    tid = int(parts[1])
    conn = _conn(context)
    cur = await conn.execute("DELETE FROM triggers WHERE id = ?", (tid,))
    if cur.rowcount > 0:
        await update.message.reply_text(f"✅ Trigger ID {tid} dihapus.")
    else:
        await update.message.reply_text("Trigger tidak ditemukan.")
    await conn.commit()

async def check_and_execute_trigger(conn, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Returns True if a trigger was executed."""
    # check if admin is drafting a trigger
    draft = context.user_data.get("trigger_draft")
    if draft:
        draft["messages"].append(text)
        await update.message.reply_text("Pesan ditambahkan ke draft trigger. Kirim lagi atau ketik /selesai_trigger")
        return True
        
    text_lower = text.strip().lower()
    cur = await conn.execute("SELECT actions_json FROM triggers WHERE keyword = ?", (text_lower,))
    row = await cur.fetchone()
    if not row:
        return False
        
    actions = json.loads(row["actions_json"])
    for msg in actions:
        await update.message.reply_text(msg)
    return True
