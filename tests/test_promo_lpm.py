import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, Chat, User

from bot.database import Database
from bot.handlers.promo import verify_lpm_link_embed, lpm_cmd

@pytest.mark.asyncio
async def test_verify_lpm_link_embed_real_link():
    db = Database()
    conn = await db.connect()
    try:
        # Upsert test user
        user_id = 1073487310
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=user_id,
            username="placiox",
            first_name="क eral",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )

        mock_html = """
        <div class="tgme_widget_message_author accent_color">
            <a class="tgme_widget_message_author_name" href="https://t.me/placiox">
                <span dir="auto">क eral</span>
            </a>&nbsp;in&nbsp;
            <a class="tgme_widget_message_owner_name" href="https://t.me/sirkuse">
                <span dir="auto">tes lpm</span>
            </a>
        </div>
        <div class="tgme_widget_message_text js-message_text" dir="auto">dhruva</div>
        """
        link = "https://t.me/sirkuse/27"

        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            is_valid, status_code, err_msg = await verify_lpm_link_embed(
                conn, db, user_id=user_id, link=link, lpm_keyword="dhruva"
            )
            assert is_valid is True
            assert status_code == "VALID"
            assert err_msg is None

            # Test with wrong keyword
            is_valid_wrong_kw, status_wrong, err_wrong = await verify_lpm_link_embed(
                conn, db, user_id=user_id, link=link, lpm_keyword="nonexistentkeyword999"
            )
            assert is_valid_wrong_kw is False
            assert status_wrong == "NO_KEYWORD"

            # Test with non-matching sender
            is_valid_wrong_sender, status_sender, err_sender = await verify_lpm_link_embed(
                conn, db, user_id=99999999, link=link, lpm_keyword="dhruva"
            )
            assert is_valid_wrong_sender is False
            assert status_sender in ("USER_NOT_FOUND", "SENDER_MISMATCH")
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_lpm_cmd_interactive_responses():
    db = Database()
    conn = await db.connect()
    try:
        user_id = 1073487310
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=user_id,
            username="placiox",
            first_name="क eral",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )

        # Mock Update and Message
        update = MagicMock()
        update.effective_user.id = user_id
        update.message = MagicMock()
        
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        status_msg.reply_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        link = "https://t.me/sirkuse/27"
        await conn.execute("DELETE FROM promo_verifications WHERE link = ?", (link,))

        context = MagicMock()
        context.bot_data = {"db": db, "conn": conn}
        context.args = [link]

        from unittest.mock import patch
        with patch("bot.handlers.promo.verify_lpm_link_embed", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = (True, "VALID", None)
            await lpm_cmd(update, context)

        # Verify initial waiting message was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        assert "Sedang Memvalidasi Link LPM" in call_args

        # Verify message was edited with success
        status_msg.edit_text.assert_called_once()
        edit_args = status_msg.edit_text.call_args[0][0]
        assert "Berhasil Divalidasi" in edit_args
        assert "+1 Agra" in edit_args

    finally:
        try:
            await conn.execute("DELETE FROM promo_verifications WHERE link = ?", ("https://t.me/sirkuse/27",))
        except Exception:
            pass
        await conn.close()

def test_normalize_telegram_post_and_story_links():
    from bot.handlers.promo import normalize_telegram_post_link, normalize_telegram_story_link

    # Standard
    assert normalize_telegram_post_link("https://t.me/grup_lpm/123") == "https://t.me/grup_lpm/123"
    # Case insensitive username & trailing slash
    assert normalize_telegram_post_link("https://t.me/Grup_Lpm/123/") == "https://t.me/grup_lpm/123"
    # Query parameters (?single or ?comment)
    assert normalize_telegram_post_link("https://t.me/grup_lpm/123?single") == "https://t.me/grup_lpm/123"
    assert normalize_telegram_post_link("http://telegram.me/grup_lpm/123?comment=456") == "https://t.me/grup_lpm/123"
    # Private link format
    assert normalize_telegram_post_link("https://t.me/c/123456789/45") == "https://t.me/c/123456789/45"
    # Invalid links
    assert normalize_telegram_post_link("https://google.com") is None
    assert normalize_telegram_post_link("https://t.me/notapost") is None
    assert normalize_telegram_post_link("") is None

    # Story link
    assert normalize_telegram_story_link("https://t.me/Username/s/15") == "https://t.me/username/s/15"
    assert normalize_telegram_story_link("https://t.me/username/s/15?extra=1") == "https://t.me/username/s/15"
    assert normalize_telegram_story_link("https://t.me/username/15") is None

@pytest.mark.asyncio
async def test_lpm_cmd_blocks_duplicates_and_variations():
    from bot.handlers.promo import lpm_cmd
    db = Database()
    conn = await db.connect()
    try:
        user_id = 1073487310
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=user_id,
            username="placiox",
            first_name="क eral",
            last_name="",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )

        canon_link = "https://t.me/sirkuse/27"
        await conn.execute("DELETE FROM promo_verifications WHERE link = ?", (canon_link,))
        await conn.commit()

        # 1. Simulate already VALID in database
        await db.add_promo_verification(conn, user_id, canon_link, promo_type="lpm", status="VALID")
        
        update = MagicMock()
        update.effective_user.id = user_id
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.bot_data = {"db": db, "conn": conn}
        # User enters variation with ?single and uppercase
        context.args = ["https://t.me/Sirkuse/27?single"]

        await lpm_cmd(update, context)

        update.message.reply_text.assert_called_once()
        msg_text = update.message.reply_text.call_args[0][0]
        assert "sudah pernah divalidasi" in msg_text

        # 2. Simulate currently PROCESSING in database
        await conn.execute("UPDATE promo_verifications SET status = 'PROCESSING' WHERE link = ?", (canon_link,))
        await conn.commit()

        update.message.reply_text.reset_mock()
        await lpm_cmd(update, context)
        update.message.reply_text.assert_called_once()
        msg_text = update.message.reply_text.call_args[0][0]
        assert "Sedang Diproses" in msg_text or "proses validasi" in msg_text

        # 3. Simulate PENDING in database
        await conn.execute("UPDATE promo_verifications SET status = 'PENDING' WHERE link = ?", (canon_link,))
        await conn.commit()

        update.message.reply_text.reset_mock()
        await lpm_cmd(update, context)
        update.message.reply_text.assert_called_once()
        msg_text = update.message.reply_text.call_args[0][0]
        assert "Sedang Diproses" in msg_text or "antrean" in msg_text

    finally:
        try:
            await conn.execute("DELETE FROM promo_verifications WHERE link = ?", ("https://t.me/sirkuse/27",))
            await conn.commit()
        except Exception:
            pass
        await conn.close()

@pytest.mark.asyncio
async def test_promo_queue_atomic_locking():
    from bot.jobs import process_promo_queue
    db = Database()
    conn = await db.connect()
    try:
        user_id = 1073487310
        link = "https://t.me/sirkuse/27"
        await conn.execute("DELETE FROM promo_verifications WHERE link = ?", (link,))
        await conn.commit()

        # Add row with PROCESSING status (as if foreground lpm_cmd is working on it)
        req_id = await db.add_promo_verification(conn, user_id, link, promo_type="lpm", status="PROCESSING")

        # Record initial agra balance
        initial_agra = await db.agra_total(conn, user_id)

        # Run process_promo_queue
        context = MagicMock()
        context.bot_data = {"db": db, "conn": conn}
        context.bot.send_message = AsyncMock()

        await process_promo_queue(context)

        # Confirm queue did NOT process or award Agra because status was PROCESSING
        cur_row = await db.get_promo_link_record(conn, link)
        assert cur_row["status"] == "PROCESSING"
        after_agra = await db.agra_total(conn, user_id)
        assert after_agra == initial_agra
        context.bot.send_message.assert_not_called()

    finally:
        try:
            await conn.execute("DELETE FROM promo_verifications WHERE link = ?", ("https://t.me/sirkuse/27",))
            await conn.commit()
        except Exception:
            pass
        await conn.close()

