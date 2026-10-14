import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat
from bot.database import Database, ROLE_OWNER, ROLE_INTERNAL, ROLE_PURVA
from bot.handlers import commands

def make_mock_update(user_id=99991, text=""):
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "Boss"
    user.last_name = "Owner"
    user.username = "boss"
    update.effective_user = user
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = user_id
    update.effective_chat.type = "private"
    
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.message_id = 1001
    msg.reply_text = AsyncMock()
    msg.chat_id = user_id
    update.effective_message = msg
    update.message = msg
    return update

@pytest.mark.asyncio
async def test_daftar_all_staf_and_purva():
    db = Database()
    conn = await db.connect()

    owner_id = 999991
    staff_id = 999992
    purva_id = 999993

    # Clean up any leftover test data
    for uid in (owner_id, staff_id, purva_id):
        try:
            await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id = ? OR actor_telegram_id = ?", (uid, uid))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
        except Exception:
            pass
    await conn.commit()

    try:
        # Insert users
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=owner_id,
            username="boss",
            first_name="Boss",
            last_name="Owner",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={"full_name": "Boss Owner"}
        )
        await db.set_role(conn, owner_id, ROLE_OWNER)

        await db.upsert_user_from_telegram(
            conn,
            telegram_id=staff_id,
            username="staff1",
            first_name="Staff",
            last_name="Internal",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={"full_name": "Staff Internal"}
        )
        await db.set_role(conn, staff_id, ROLE_INTERNAL)

        await db.upsert_user_from_telegram(
            conn,
            telegram_id=purva_id,
            username="alumni1",
            first_name="Alumni",
            last_name="Purva",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={"full_name": "Alumni Purva"}
        )
        await db.set_role(conn, purva_id, ROLE_PURVA)

        # Add agra for purva
        await db.add_agra(
            conn,
            target_id=purva_id,
            actor_id=owner_id,
            amount=500,
            description="test_purva_bonus",
            chat_id=None,
            message_id=None,
        )
        await conn.commit()

        app = MagicMock()
        app.bot_data = {"db": db, "conn": conn}

        ctx = MagicMock()
        ctx.application = app

        # 1. Test /daftar charya (Staf, Admin, Owner)
        u1 = make_mock_update(user_id=owner_id, text="/daftar charya")
        ctx.args = ["charya"]
        await commands.cmd_daftar(u1, ctx)
        assert u1.message.reply_text.called
        replies = [call.args[0] for call in u1.message.reply_text.call_args_list]
        assert any("Daftar Charya" in r and "Staff Internal" in r for r in replies)

        # 1b. Test /daftar help menu doesn't have dangling all_staf
        u_help = make_mock_update(user_id=owner_id, text="/daftar")
        ctx.args = []
        await commands.cmd_daftar(u_help, ctx)
        assert u_help.message.reply_text.called
        help_replies = [call.args[0] for call in u_help.message.reply_text.call_args_list]
        assert not any("all_staf" in r for r in help_replies)
        assert any("/daftar charya" in r for r in help_replies)

        # 2. Test /daftar purva
        u2 = make_mock_update(user_id=owner_id, text="/daftar purva")
        ctx.args = ["purva"]
        await commands.cmd_daftar(u2, ctx)
        assert u2.message.reply_text.called
        replies2 = [call.args[0] for call in u2.message.reply_text.call_args_list]
        assert any("Daftar Purva (Alumni)" in r and "Alumni Purva" in r for r in replies2)

        # 3. Test /agratop purva
        u3 = make_mock_update(user_id=owner_id, text="/agratop purva")
        ctx.args = ["purva"]
        await commands.cmd_agratop(u3, ctx)
        assert u3.message.reply_text.called
        replies3 = [call.args[0] for call in u3.message.reply_text.call_args_list]
        print(f"REPLIES3: {replies3}")
        assert any("Purva" in r for r in replies3)

    finally:
        for uid in (owner_id, staff_id, purva_id):
            try:
                await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id = ? OR actor_telegram_id = ?", (uid, uid))
                await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
            except Exception:
                pass
        await conn.commit()
        await conn.close()
