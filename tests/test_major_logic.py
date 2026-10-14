import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Update, Message, Chat, User, CallbackQuery
from bot.database import Database
from bot.handlers import commands

class MockUser:
    def __init__(self, id):
        self.id = id
        self.first_name = "Test"
        self.last_name = "User"
        self.username = "testuser"
        self.language_code = "id"
        self.is_bot = False
        self.is_premium = None
        self.added_to_attachment_menu = None
        self.can_connect_to_business = None
        self.allows_write_to_pm = None

    def to_dict(self):
        return {"id": self.id, "username": self.username}

class MockChat:
    def __init__(self):
        self.type = "private"

class MockMessage:
    def __init__(self, id):
        self.message_id = 1234
        self.chat_id = id
        self.chat = MockChat()
        self.text = "Mock message"
        self.reply_text = AsyncMock()

class MockCallbackQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.message = MockMessage(user_id)
        self.from_user = MockUser(user_id)

def create_mock_update_callback(data, user_id=111111):
    update = MagicMock(spec=Update)
    update.effective_user = MockUser(user_id)
    update.callback_query = MockCallbackQuery(data, user_id)
    update.message = None
    return update

def create_mock_update_msg(text="/start", user_id=111111):
    update = MagicMock(spec=Update)
    update.effective_user = MockUser(user_id)
    msg = MockMessage(user_id)
    msg.text = text
    update.message = msg
    return update

def create_mock_context(db, conn):
    context = MagicMock()
    context.application = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {}
    return context

@pytest.mark.asyncio
async def test_chained_major_selection():
    print("=== Testing Chained Major Selection ===")
        
    db = Database()
    conn = await db.connect()
    
    u1 = 111111
    ctx = create_mock_context(db, conn)
    
    print("\n[1] Manually create user")
    await conn.execute(
        """
        INSERT OR REPLACE INTO users (telegram_id, username, first_name, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (u1, "testuser", "Test", "student", 1000000, 1000000)
    )
    await conn.commit()
    print("Role set to 'student'")
    
    print("\n[2] /lengkapi -> Click Jurusan (openlc:major)")
    upd = create_mock_update_callback("openlc:major", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    assert "Pilih <b>Fakultas</b> terlebih dahulu" in msg
    
    print("\n[3] Click Fakultas FMIPA (lc_fac_for_maj:faculty:fmipa)")
    upd = create_mock_update_callback("lc_fac_for_maj:faculty:fmipa", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    
    # DEBUG
    row = await db.get_user(conn, u1)
    print(f"DEBUG After Fac: raw_profile={row['raw_profile_json']} profile={row['profile_json']}")
    
    assert "Sekarang pilih <b>Jurusan</b>" in msg
    
    print("\n[4] Click Jurusan Ilmu Kimia (lc:major:ik)")
    upd = create_mock_update_callback("lc:major:ik", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    
    import json
    row = await db.get_user(conn, u1)
    prof = json.loads(row["profile_json"])
    print(f"Saved Profile: faculty={prof.get('faculty')}, major={prof.get('major')}")
    assert prof.get('faculty') == 'fmipa'
    assert prof.get('major') == 'ik'
    
    print("\n[5] /ubah -> Click Jurusan (openec:major)")
    upd = create_mock_update_callback("openec:major", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    assert "Pilih <b>Fakultas</b> terlebih dahulu" in msg
    
    print("\n[6] Click Fakultas FIB (ec_fac_for_maj:faculty:fib)")
    upd = create_mock_update_callback("ec_fac_for_maj:faculty:fib", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    assert "Sekarang pilih <b>Jurusan</b>" in msg
    print(f"Temp data in context: {ctx.user_data}")
    
    print("\n[7] Click Jurusan Seni Musik (ec:major:sm)")
    upd = create_mock_update_callback("ec:major:sm", u1)
    await commands.on_callback(upd, ctx)
    msg = upd.callback_query.edit_message_text.call_args[0][0]
    print(f"Bot says: {msg.encode('ascii', 'ignore').decode('ascii')!r}")
    
    reqs = await db.list_pending_profile_requests(conn)
    print(f"\nPending Requests: {len(reqs)}")
    if reqs:
        req = reqs[0]
        prop = json.loads(req["proposed_json"])
        print(f"Proposed changes: {prop}")
        assert prop.get('faculty') == 'fib'
        assert prop.get('major') == 'sm'
        
        await db.resolve_profile_request(conn, req["id"], True, 999)
        row = await db.get_user(conn, u1)
        prof = json.loads(row["profile_json"])
        print(f"Saved Profile after approve: faculty={prof.get('faculty')}, major={prof.get('major')}")
        assert prof.get('faculty') == 'fib'
        assert prof.get('major') == 'sm'
        
    await conn.close()
    print("\n=== All Tests Passed ===")

if __name__ == "__main__":
    asyncio.run(test_chained_major_selection())
