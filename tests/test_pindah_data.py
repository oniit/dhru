import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.database import Database, ROLE_OWNER, ROLE_STUDENT
from bot.handlers.commands import cmd_pindah_data

@pytest.mark.asyncio
async def test_migrate_user_data_logic():
    db = Database()
    conn = await db.connect()
    try:
        # Cleanup dulu jika ada sisa (hapus child table dulu)
        await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id IN (?, ?)", (88801, 88802))
        await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (88801, 88802))
        await conn.commit()

        # Buat user lama
        await db.upsert_user_from_telegram(
            conn, telegram_id=88801, username="old_user_test", first_name="Old", last_name="User",
            language_code="id", is_premium=False, is_bot=False, raw_profile={"faculty": "saintek"}
        )
        await db.set_role(conn, 88801, ROLE_STUDENT)
        await db.add_agra(conn, target_id=88801, actor_id=88801, amount=77, description="Poin tes", chat_id=None, message_id=None)
        
        # Migrasi ke user baru yang belum ada di users
        success = await db.migrate_user_data(conn, 88801, 88802)
        assert success is True
        
        old_u = await db.get_user(conn, 88801)
        assert old_u is None
        
        new_u = await db.get_user(conn, 88802)
        assert new_u is not None
        assert new_u["first_name"] == "Old"
        assert new_u["role"] == ROLE_STUDENT
        
        # Cek ledger
        total_agra = await db.agra_total(conn, 88802)
        assert total_agra == 77
    finally:
        # Cleanup child dulu baru parent
        try:
            await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id IN (?, ?)", (88801, 88802))
            await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (88801, 88802))
            await conn.commit()
            await conn.close()
        except Exception:
            pass

@pytest.mark.asyncio
async def test_cmd_pindah_data_bracket_sanitization():
    db = Database()
    conn = await db.connect()
    try:
        # Cleanup dulu
        await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (99901, 99902))
        await conn.commit()

        await db.upsert_user_from_telegram(
            conn, telegram_id=99901, username="bracket_old", first_name="BracketOld", last_name="",
            language_code="id", is_premium=False, is_bot=False, raw_profile={}
        )
        await db.set_role(conn, 99901, ROLE_STUDENT)
        
        # Setup mock update & context
        update = MagicMock()
        update.effective_user.id = 99999
        update.message.reply_text = AsyncMock()
        
        context = MagicMock()
        context.application.bot_data = {"db": db, "conn": conn}
        # Input dengan kurung siku < >
        context.args = ["<99901>", "<99902>"]
        
        # Mock is_owner
        import bot.handlers.commands as cmds
        original_is_owner = cmds.is_owner
        cmds.is_owner = lambda uid: True
        
        try:
            await cmd_pindah_data(update, context)
            update.message.reply_text.assert_called()
            last_call = update.message.reply_text.call_args[0][0]
            assert "Berhasil memindahkan data" in last_call
            assert "99901" in last_call
            assert "99902" in last_call
            
            migrated_u = await db.get_user(conn, 99902)
            assert migrated_u is not None
            assert migrated_u["first_name"] == "BracketOld"
        finally:
            cmds.is_owner = original_is_owner
    finally:
        try:
            await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (99901, 99902))
            await conn.commit()
            await conn.close()
        except Exception:
            pass
