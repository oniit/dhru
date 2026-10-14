import pytest
from unittest.mock import MagicMock
from bot.jobs import is_keep_msg_excluded


def test_is_keep_msg_excluded():
    bot_id = 123456789

    # 1. Error message reported by user (must be excluded)
    msg_err = MagicMock()
    msg_err.empty = False
    msg_err.service = False
    msg_err.from_user = None
    msg_err.caption = None
    msg_err.text = (
        "❌ Gagal! Terjadi kesalahan saat mem-forward pesan:\n"
        'Telegram says: [400 MESSAGE_ID_INVALID] (caused by "messages.ForwardMessages") '
        "Pyrogram 2.3.69 thinks: The message id is invalid"
    )
    assert is_keep_msg_excluded(msg_err, bot_id) is True

    # 2. Success notification message (must be excluded)
    msg_succ = MagicMock()
    msg_succ.empty = False
    msg_succ.service = False
    msg_succ.from_user = None
    msg_succ.caption = None
    msg_succ.text = "✅ Cek @DhruvaPoster, 15 pesan di atas telah diforward ke sana."
    assert is_keep_msg_excluded(msg_succ, bot_id) is True

    # 3. Message from bot user object (must be excluded)
    msg_from_bot = MagicMock()
    msg_from_bot.empty = False
    msg_from_bot.service = False
    msg_from_bot.from_user = MagicMock()
    msg_from_bot.from_user.is_bot = True
    msg_from_bot.from_user.id = 999999
    msg_from_bot.text = "Pesan bot acak"
    assert is_keep_msg_excluded(msg_from_bot, bot_id) is True

    # 4. Message from our bot ID (must be excluded)
    msg_our_bot = MagicMock()
    msg_our_bot.empty = False
    msg_our_bot.service = False
    msg_our_bot.from_user = MagicMock()
    msg_our_bot.from_user.is_bot = False
    msg_our_bot.from_user.id = bot_id
    msg_our_bot.text = "Pesan status"
    assert is_keep_msg_excluded(msg_our_bot, bot_id) is True

    # 5. Empty or deleted stub message (must be excluded)
    msg_empty = MagicMock()
    msg_empty.empty = True
    msg_empty.service = False
    assert is_keep_msg_excluded(msg_empty, bot_id) is True

    # 6. Telegram service message (e.g. pinned message, photo changed) (must be excluded)
    msg_service = MagicMock()
    msg_service.empty = False
    msg_service.service = True
    assert is_keep_msg_excluded(msg_service, bot_id) is True

    # 7. Normal user text message (must NOT be excluded, must forward)
    msg_user_text = MagicMock()
    msg_user_text.empty = False
    msg_user_text.service = False
    msg_user_text.from_user = MagicMock()
    msg_user_text.from_user.is_bot = False
    msg_user_text.from_user.id = 555555
    msg_user_text.text = "Pengumuman jadwal kuliah semester ganjil 2026/2027."
    assert is_keep_msg_excluded(msg_user_text, bot_id) is False

    # 8. Normal photo post with caption (must NOT be excluded, must forward)
    msg_photo = MagicMock()
    msg_photo.empty = False
    msg_photo.service = False
    msg_photo.from_user = None
    msg_photo.text = None
    msg_photo.caption = "Flyer Workshop Desain Grafis Dhruva 2026"
    assert is_keep_msg_excluded(msg_photo, bot_id) is False

    # 9. Poll message (no text, no caption) (must NOT be excluded, must forward!)
    msg_poll = MagicMock()
    msg_poll.empty = False
    msg_poll.service = False
    msg_poll.from_user = None
    msg_poll.text = None
    msg_poll.caption = None
    msg_poll.poll = MagicMock()
    assert is_keep_msg_excluded(msg_poll, bot_id) is False

    # 10. Contact / location / sticker / any arbitrary Telegram message type (must NOT be excluded, must forward!)
    msg_other = MagicMock()
    msg_other.empty = False
    msg_other.service = False
    msg_other.from_user = None
    msg_other.text = None
    msg_other.caption = None
    msg_other.contact = MagicMock()
    assert is_keep_msg_excluded(msg_other, bot_id) is False
