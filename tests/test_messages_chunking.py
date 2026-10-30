import html
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Chat, Message
from bot.handlers.messages import chunk_text_html, on_private_message
import bot.handlers.messages as msg_mod
import bot.handlers.triggers as trig_mod


def run_sync(coro):
    """Drive pure async coroutines that only await AsyncMocks without asyncio event loop sockets."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


def test_chunk_text_html_short():
    assert chunk_text_html("") == []
    res = chunk_text_html("Halo dunia", max_len=50)
    assert res == ["Halo dunia"]


def test_chunk_text_html_multiline():
    lines = ["Line " + str(i) + "\n" for i in range(100)]
    long_text = "".join(lines)
    chunks = chunk_text_html(long_text, max_len=100)
    assert len(chunks) > 1
    # Check that recombined chunks equal original text
    assert "".join(chunks) == long_text
    # Check that every chunk escaped is <= max_len
    for c in chunks:
        assert len(html.escape(c)) <= 100


def test_chunk_text_html_no_newlines():
    long_line = "A" * 500
    chunks = chunk_text_html(long_line, max_len=100)
    assert len(chunks) == 5
    assert "".join(chunks) == long_line
    for c in chunks:
        assert len(html.escape(c)) <= 100


def test_chunk_text_html_html_entities_expansion():
    # Test that expansion of < > & does not violate max_len
    raw = "<tag>" * 30  # each is 5 chars, but escaped is 17 chars (&lt;tag&gt;)
    chunks = chunk_text_html(raw, max_len=50)
    assert "".join(chunks) == raw
    for c in chunks:
        assert len(html.escape(c)) <= 50


def test_on_private_message_chunking(monkeypatch):
    test_uid = 888777111

    # Mock user_row and check_and_execute_trigger
    fake_row = {
        "telegram_id": test_uid,
        "username": "longtexter",
        "role": "public",
        "onboarding_step": None,
    }
    monkeypatch.setattr(msg_mod, "user_row", AsyncMock(return_value=fake_row))
    monkeypatch.setattr(trig_mod, "check_and_execute_trigger", AsyncMock(return_value=False))

    # Set PETINGGI_GID
    fake_petinggi_gid = -10099887766
    monkeypatch.setattr(msg_mod, "PETINGGI_GID", fake_petinggi_gid)

    bot_mock = MagicMock()
    first_sent_msg = MagicMock(message_id=54321)
    bot_mock.send_message = AsyncMock(return_value=first_sent_msg)
    context_mock = MagicMock()
    context_mock.bot = bot_mock
    context_mock.user_data = {}
    context_mock.application.bot_data = {"conn": MagicMock(), "db": MagicMock()}

    # 1. Test short message: single send_message call
    update_short = MagicMock(spec=Update)
    update_short.effective_user = MagicMock(spec=User, id=test_uid, first_name="Long", username="longtexter")
    update_short.effective_chat = MagicMock(spec=Chat, id=test_uid, type="private")
    update_short.message = MagicMock(spec=Message, text="Pesan pendek saja", caption=None, sticker=None, video_note=None)
    update_short.message.reply_text = AsyncMock()

    run_sync(on_private_message(update_short, context_mock))
    assert bot_mock.send_message.call_count == 1
    call_kwargs = bot_mock.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == fake_petinggi_gid
    assert "Pesan pendek saja" in call_kwargs["text"]
    assert "(1/" not in call_kwargs["text"]

    # 2. Test long message (> 4000 characters): chunked into multiple messages
    bot_mock.reset_mock()
    bot_mock.send_message = AsyncMock(return_value=first_sent_msg)

    long_msg = "Paragraf penting yang sangat panjang.\n" * 150  # ~6000 chars
    update_long = MagicMock(spec=Update)
    update_long.effective_user = MagicMock(spec=User, id=test_uid, first_name="Long", username="longtexter")
    update_long.effective_chat = MagicMock(spec=Chat, id=test_uid, type="private")
    update_long.message = MagicMock(spec=Message, text=long_msg, caption=None, sticker=None, video_note=None)
    update_long.message.reply_text = AsyncMock()

    run_sync(on_private_message(update_long, context_mock))
    assert bot_mock.send_message.call_count >= 2
    calls = bot_mock.send_message.call_args_list

    # First chunk
    first_call = calls[0].kwargs
    assert "(1/" in first_call["text"]
    assert "#ID_888777111" in first_call["text"]
    assert len(first_call["text"]) <= 4096

    # Second chunk
    second_call = calls[1].kwargs
    assert "[Lanjutan #ID_888777111 (2/" in second_call["text"]
    assert second_call["reply_to_message_id"] == 54321
    assert len(second_call["text"]) <= 4096
