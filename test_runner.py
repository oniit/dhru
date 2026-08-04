import asyncio
import os
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, Chat, User
from bot.database import Database
from bot.handlers import commands, menfess, attendance, triggers, tugas, ktm, karpeg, kontrak, broadcast

logging.basicConfig(level=logging.ERROR)

def create_mock_update(text="/start", user_id=111111, chat_type="private"):
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = user_id
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.effective_user.username = "testuser"
    update.effective_user.language_code = "id"
    update.effective_user.is_bot = False
    update.effective_user.is_premium = None
    update.effective_user.added_to_attachment_menu = None
    update.effective_user.can_connect_to_business = None
    update.effective_user.allows_write_to_pm = None
    
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.chat_id = user_id if chat_type == "private" else -100123456789
    msg.chat = MagicMock(spec=Chat)
    msg.chat.type = chat_type
    msg.from_user = update.effective_user
    msg.reply_text = AsyncMock()
    msg.reply_html = AsyncMock()
    update.message = msg
    
    return update

def create_mock_context(db, conn, args=None):
    context = MagicMock()
    context.application = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.get_chat = AsyncMock()
    context.args = args or []
    return context

async def run_tests():
    print("=== Memulai Tes Otomatis ===")
    os.environ["TURSO_DATABASE_URL"] = "file:test_db.sqlite3"
    
    if os.path.exists("test_db.sqlite3"):
        os.remove("test_db.sqlite3")
        
    db = Database()
    conn = await db.connect()
    
    # 1. Test /start
    print("Testing /start...")
    u = create_mock_update("/start")
    c = create_mock_context(db, conn)
    await commands.cmd_start(u, c)
    
    # Check if user was created
    row = await db.get_user(conn, 111111)
    if row:
        print(f" -> User created: {row['telegram_id']}")
    else:
        print(" -> GAGAL: User tidak ada!")
        
    # Promote to owner for further testing
    await db.set_role(conn, 111111, "owner")
    
    # Test all commands with empty or dummy args
    command_funcs = [
        ("help", commands.cmd_help, []),
        ("profile", commands.cmd_profile, []),
        ("lengkapi", commands.cmd_lengkapi, []),
        ("ubah", commands.cmd_ubah, []),
        ("add", commands.cmd_add, ["100", "@testuser"]),
        ("transfer", commands.cmd_transfer, ["10", "@testuser"]),
        ("agralog", commands.cmd_agralog, []),
        ("setrole", commands.cmd_setrole, []),
        ("daftar", commands.cmd_daftar, []),
        ("detail", commands.cmd_detail, ["111111"]),
        ("admin_data", commands.cmd_admin_data, ["111111"]),
        ("pending", commands.cmd_pending, []),
        ("log", commands.cmd_log, []),
        ("tagall", commands.cmd_tagall, []),
        ("all", commands.cmd_all, []),
        ("cek_user", commands.cmd_cek_user, ["111111"]),
        ("users", commands.cmd_users, ["stats"]),
        ("menfess_read", menfess.cmd_menfess_read, ["1"]),
        ("presensi", attendance.cmd_presensi_router, []),
        ("hadir", attendance.cmd_hadir, ["123"]),
        ("trigger", triggers.cmd_trigger_router, []),
        ("agra", commands.cmd_agra_router, []),
        ("gencode", commands.cmd_gencode, []),
        ("broadcast", broadcast.cmd_broadcast, ["public", "test"]),
    ]
    
    errors = 0
    for name, func, args in command_funcs:
        print(f"Testing /{name}...", end=" ")
        try:
            u = create_mock_update(f"/{name} {' '.join(args)}".strip())
            c = create_mock_context(db, conn, args)
            await func(u, c)
            print(f"-> OK")
        except Exception as e:
            print(f"-> ERROR: {e}")
            import traceback
            traceback.print_exc()
            errors += 1
            
    await conn.close()
    if os.path.exists("test_db.sqlite3"):
        os.remove("test_db.sqlite3")
        
    print(f"=== Selesai dengan {errors} Error ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
