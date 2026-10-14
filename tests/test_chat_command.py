import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, Chat, User
from telegram.error import Forbidden, BadRequest

from bot.database import Database
from bot.handlers.common import resolve_target_user, send_message_or_media_to_target
from bot.handlers import commands
import bot.settings

@pytest.mark.asyncio
async def test_resolve_target_user():
    db = Database()
    conn = await db.connect()
    
    try:
        # Setup test users in DB
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=12345,
            username="alice_test",
            first_name="Alice",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )
        
        # 1. Numeric ID
        tid, desc = await resolve_target_user(conn, db, "12345")
        assert tid == 12345
        assert "Alice" in desc
        
        # 2. Username in users table
        tid, desc = await resolve_target_user(conn, db, "@alice_test")
        assert tid == 12345
        assert "Alice" in desc
        
        # 2b. Username without @ in users table
        tid, desc = await resolve_target_user(conn, db, "alice_test")
        assert tid == 12345
        
        # 3. Username in group_seen_users
        await db.touch_group_seen_user(conn, chat_id=-1001, telegram_id=67890, username="bob_group", first_name="Bob", last_name="", is_bot=False)
        
        tid, desc = await resolve_target_user(conn, db, "@bob_group")
        assert tid == 67890
        assert "Bob" in desc
        
        # 4. Unknown user without IPC response
        tid, desc = await resolve_target_user(conn, db, "@non_existent_user_xyz")
        assert tid is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_message_or_media_to_target():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    
    # 1. Plain text direct
    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.video = None
    msg.document = None
    msg.audio = None
    msg.voice = None
    msg.animation = None
    msg.sticker = None
    msg.video_note = None
    msg.text = "/chat @user Halo"
    
    await send_message_or_media_to_target(bot, 123, msg, text_or_caption="Halo")
    bot.send_message.assert_called_with(chat_id=123, text="Halo", parse_mode=None)
    
    # 2. Direct photo
    msg_photo = MagicMock(spec=Message)
    msg_photo.photo = [MagicMock()]
    msg_photo.video = None
    msg_photo.document = None
    msg_photo.audio = None
    msg_photo.voice = None
    msg_photo.animation = None
    msg_photo.sticker = None
    msg_photo.video_note = None
    msg_photo.copy = AsyncMock()
    
    await send_message_or_media_to_target(bot, 123, msg_photo, text_or_caption="Lihat foto ini")
    msg_photo.copy.assert_called_with(chat_id=123, caption="Lihat foto ini", parse_mode=None)
    
    # 3. Reply to photo
    replied_photo = MagicMock(spec=Message)
    replied_photo.photo = [MagicMock()]
    replied_photo.video = None
    replied_photo.document = None
    replied_photo.audio = None
    replied_photo.voice = None
    replied_photo.animation = None
    replied_photo.sticker = None
    replied_photo.video_note = None
    replied_photo.caption = "Caption Asli"
    replied_photo.copy = AsyncMock()
    
    # 3a. Override caption
    await send_message_or_media_to_target(bot, 123, msg, text_or_caption="Caption Baru", source_message=replied_photo)
    replied_photo.copy.assert_called_with(chat_id=123, caption="Caption Baru", parse_mode=None)
    
    # 3b. Keep caption if no extra text
    await send_message_or_media_to_target(bot, 123, msg, text_or_caption="", source_message=replied_photo)
    replied_photo.copy.assert_called_with(chat_id=123, caption="Caption Asli", parse_mode=None)


@pytest.mark.asyncio
async def test_cmd_chat_permissions_and_flow():
    db = Database()
    conn = await db.connect()
    
    try:
        # Mock bot.settings.OWNER_ID
        bot.settings.OWNER_ID = 999
        
        # 1. Non-owner test
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 111  # Not owner
        update.message = MagicMock(spec=Message)
        update.message.reply_text = AsyncMock()
        
        context = MagicMock()
        context.application.bot_data = {"conn": conn, "db": db}
        
        await commands.cmd_chat(update, context)
        update.message.reply_text.assert_called_with("⛔ Perintah ini khusus Owner.")
        
        # 2. Owner test with missing arguments
        update.effective_user.id = 999  # Owner
        update.message.text = "/chat"
        update.message.caption = None
        update.message.reply_to_message = None
        update.message.photo = None
        update.message.video = None
        update.message.document = None
        update.message.audio = None
        update.message.voice = None
        update.message.animation = None
        update.message.sticker = None
        update.message.video_note = None
        
        await commands.cmd_chat(update, context)
        assert "Format Penggunaan" in update.message.reply_text.call_args[0][0]
        
        # 3. Owner test sending message to valid user
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=555,
            username="charlie",
            first_name="Charlie",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )
        
        update.message.text = "/chat @charlie Halo Charlie dari Owner!"
        context.bot.send_message = AsyncMock()
        
        await commands.cmd_chat(update, context)
        context.bot.send_message.assert_called_with(chat_id=555, text="Halo Charlie dari Owner!", parse_mode=None)
        assert "Pesan berhasil dikirim" in update.message.reply_text.call_args[0][0]
        
        # 4. Owner test error handling (user hasn't started bot)
        context.bot.send_message = AsyncMock(side_effect=BadRequest("Bad Request: chat not found"))
        await commands.cmd_chat(update, context)
        assert "belum pernah memulai" in update.message.reply_text.call_args[0][0]

        # 5. Owner test sending photo with caption and message text
        update.message.text = None
        update.message.caption = "/chat @charlie Ini foto tugas!"
        update.message.photo = [MagicMock()]
        update.message.copy = AsyncMock()
        
        await commands.cmd_chat(update, context)
        update.message.copy.assert_called_with(chat_id=555, caption="Ini foto tugas!", parse_mode=None)
        assert "Pesan berhasil dikirim" in update.message.reply_text.call_args[0][0]

        # 6. Owner test sending photo with caption without extra message (caption becomes empty string "")
        update.message.text = None
        update.message.caption = "/chat @charlie"
        update.message.photo = [MagicMock()]
        update.message.copy = AsyncMock()
        
        await commands.cmd_chat(update, context)
        update.message.copy.assert_called_with(chat_id=555, caption="", parse_mode=None)
        assert "Pesan berhasil dikirim" in update.message.reply_text.call_args[0][0]
    finally:
        await conn.close()

