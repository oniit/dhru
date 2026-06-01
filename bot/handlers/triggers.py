import json
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.common import user_row
from bot.database import ROLE_ADMIN, ROLE_OWNER, ROLE_STUDENT
import html

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
    if not context.args:
        await update.message.reply_text("Gunakan: /trigger add &lt;keyword&gt;")
        return
    keyword = " ".join(context.args).strip().lower()
    
    context.user_data["trigger_draft"] = {"keyword": keyword, "messages": []}
    await update.message.reply_text(f"Mulai membuat trigger untuk keyword: <code>{html.escape(keyword)}</code>\nSilakan kirim pesan balasan satu per satu.\n<i>Jika di grup, balas (reply) ke pesan ini agar bot bisa membaca pesan Anda.</i>\n\nJika sudah selesai, ketik /trigger done")

async def cmd_selesai_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    draft = context.user_data.get("trigger_draft")
    if not draft:
        await update.message.reply_text("Tidak ada draft trigger aktif. Gunakan /trigger add &lt;keyword&gt;.")
        return
    
    keyword = draft["keyword"]
    messages = draft["messages"]
    
    if not messages:
        await update.message.reply_text("Trigger dibatalkan karena tidak ada pesan.")
        context.user_data.pop("trigger_draft", None)
        return
        
    conn = _conn(context)
    actions_json = json.dumps(messages, ensure_ascii=False)
    
    try:
        await conn.execute(
            "INSERT INTO triggers (keyword, actions_json, created_by) VALUES (?, ?, ?)",
            (keyword, actions_json, update.effective_user.id)
        )
    except Exception:
        await conn.execute(
            "UPDATE triggers SET actions_json = ? WHERE keyword = ?",
            (actions_json, keyword)
        )
    await conn.commit()
    context.user_data.pop("trigger_draft", None)
    await update.message.reply_text(f"✅ Trigger untuk <code>{html.escape(keyword)}</code> berhasil disimpan dengan {len(messages)} pesan balasan.")

async def cmd_listtrigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    conn = _conn(context)
    cur = await conn.execute("SELECT * FROM triggers ORDER BY id DESC")
    rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Belum ada trigger yang terdaftar.")
        return
    lines = ["<b>Daftar Trigger:</b>"]
    for r in rows:
        lines.append(f"ID {r['id']}: <code>{html.escape(str(r['keyword']))}</code>")
    await update.message.reply_text("\n".join(lines))

async def cmd_deltrigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not await check_admin(update, context): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Gunakan: /trigger del &lt;id&gt;")
        return
    tid = int(context.args[0])
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
    if draft is not None:
        draft["messages"].append(text)
        await update.message.reply_text("Pesan ditambahkan ke draft trigger. Kirim lagi atau ketik /trigger done")
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

async def cmd_trigger_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    role = row["role"] if row else ROLE_STUDENT
    
    if role not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Maaf, Anda tidak memiliki akses ke fitur Auto-reply (Trigger).")
        return
        
    if not context.args:
        lines = [
            "<b>Auto-reply (Trigger)</b>",
            "<code>/trigger add [keyword]</code> — Tambah trigger baru",
            "<code>/trigger list</code> — Daftar trigger yang ada",
            "<code>/trigger done</code> — Menyelesaikan proses penambahan trigger",
            "<code>/trigger del [id]</code> — Hapus trigger"
        ]
        await update.message.reply_text("\n".join(lines))
        return
        
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "add": await cmd_addtrigger(update, context)
        elif subcmd == "list": await cmd_listtrigger(update, context)
        elif subcmd == "done": await cmd_selesai_trigger(update, context)
        elif subcmd in ("del", "delete"): await cmd_deltrigger(update, context)
        else: await update.message.reply_text("Sub-command Trigger tidak ditemukan. Ketik /trigger untuk panduan.")
    finally:
        context.args = original_args
