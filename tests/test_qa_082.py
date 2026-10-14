import asyncio
import os
import json
from bot.database import Database
from bot.handlers.commands import cmd_daftar
from bot.settings import CHOICES, load_choices

# Mocking Telegram Update & Context
class MockUser:
    def __init__(self, id, first_name, last_name, username):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username

class MockMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return self

class MockUpdate:
    def __init__(self, user, args=None):
        self.effective_user = user
        self.message = MockMessage()

class MockApplication:
    def __init__(self, bot_data):
        self.bot_data = bot_data

class MockContext:
    def __init__(self, application, args=None):
        self.application = application
        self.args = args or []

from pathlib import Path

async def run_tests():
    # Force local sqlite for testing
    if "TURSO_DB_URL" in os.environ:
        del os.environ["TURSO_DB_URL"]
    if "TURSO_AUTH_TOKEN" in os.environ:
        del os.environ["TURSO_AUTH_TOKEN"]
        
    db = Database(Path("test_qa_082.sqlite3"))
    conn = await db.connect()
    
    # Setup test user (Owner so they can run /daftar without restriction)
    test_user_id = int(os.environ.get("OWNER_ID", "12345") or 12345)
    os.environ["OWNER_ID"] = str(test_user_id)
    
    await conn.execute("INSERT OR REPLACE INTO users (telegram_id, username, first_name, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (test_user_id, "owner", "Owner", "owner", 0, 0))
    await conn.commit()

    bot_data = {"db": db, "conn": conn}
    app = MockApplication(bot_data)

    print("--- Test 1: Load Choices ---")
    majors = CHOICES.get("majors", [])
    print(f"Loaded {len(majors)} majors")
    for m in majors:
        print(f" - {m.get('id')}: {m.get('label')}")

    print("\n--- Test 2: /daftar (no args) Help Menu ---")
    user = MockUser(test_user_id, "Owner", "", "owner")
    update = MockUpdate(user)
    context = MockContext(app, args=[])
    
    try:
        await cmd_daftar(update, context)
        print("Reply:")
        for r in update.message.replies:
            if "ik (Kimia)" in r:
                print("[SUCCESS] Found 'ik (Kimia)' in help text")
            else:
                pass
    except Exception as e:
        print(f"[ERROR] in /daftar: {e}")

    print("\n--- Test 3: /daftar jurusan ik ---")
    update = MockUpdate(user)
    context = MockContext(app, args=["jurusan", "ik"])
    
    try:
        await cmd_daftar(update, context)
        print("Reply:")
        for r in update.message.replies:
            print(r)
            if "Daftar — Jurusan Kimia" in r:
                print("[SUCCESS] Found 'Daftar — Jurusan Kimia' in title")
            else:
                pass
    except Exception as e:
        print(f"[ERROR] in /daftar jurusan ik: {e}")
        
    print("\n--- Test 4: /daftar kelas fd ---")
    update = MockUpdate(user)
    context = MockContext(app, args=["kelas", "fd"])
    
    try:
        await cmd_daftar(update, context)
        print("Reply:")
        for r in update.message.replies:
            print(r)
            if "Daftar — Kelas Fisika Dasar" in r:
                print("[SUCCESS] Found 'Daftar — Kelas Fisika Dasar' in title")
            else:
                pass
    except Exception as e:
        print(f"[ERROR] in /daftar kelas fd: {e}")

    await conn.close()
    if os.path.exists("test_qa_082.sqlite3"):
        os.remove("test_qa_082.sqlite3")

if __name__ == "__main__":
    asyncio.run(run_tests())
