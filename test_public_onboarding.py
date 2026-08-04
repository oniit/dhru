import asyncio
import os
from pathlib import Path
from bot.database import Database
from bot.handlers.messages import on_private_message, _is_lengkapi_done
from telegram.ext import ContextTypes
from unittest.mock import AsyncMock, MagicMock
import json
from dotenv import load_dotenv

async def test_onboarding():
    load_dotenv(".env")
    os.environ["TURSO_DB_URL"] = "" # use local sqlite
    db = Database(Path("test_onboarding.sqlite3"))
    conn = await db.connect()
    try:
        
        # 1. Create public user
        uid = 999
        await db.upsert_user_from_telegram(
            conn, telegram_id=uid, username="test", first_name="Test",
            last_name=None, language_code="en", is_premium=False, is_bot=False,
            raw_profile={}
        )
        
        # Simulate /lengkapi setting the onboarding step
        await db.set_onboarding_step(conn, uid, "TEXT_LC:full_name")
        
        # 2. Simulate text message
        class FakeBot:
            async def send_message(self, chat_id, text, **kwargs):
                print(f"[BOT TO {chat_id}] {text}")
                
        class FakeApplication:
            bot_data = {"conn": conn, "db": db}
            
        class FakeContext:
            bot = FakeBot()
            application = FakeApplication()
            user_data = {}
            
        update = MagicMock()
        update.effective_user.id = uid
        update.effective_user.first_name = "Test"
        update.message.text = "Budi Santoso"
        update.message.chat_id = 999
        update.message.photo = None
        update.message.caption = None
        update.message.reply_text = AsyncMock()
        
        print("Running on_private_message...")
        await on_private_message(update, FakeContext())
        
        print("Reply calls:")
        for call in update.message.reply_text.call_args_list:
            print(f"- {call[0][0]}")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()
        if os.path.exists("test_onboarding.sqlite3"):
            os.remove("test_onboarding.sqlite3")

if __name__ == "__main__":
    asyncio.run(test_onboarding())
