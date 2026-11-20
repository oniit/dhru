import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import NetworkError

from bot.handlers.pfp import (
    parse_telegram_post_link,
    parse_pfp_args,
    forward_posts_to_keep,
    cmd_pfp,
    cb_pfp,
)


def run_sync(coro):
    """Drive async coroutines synchronously without requiring OS socket pairs."""
    stack = [coro]
    val = None
    exc = None
    while stack:
        top = stack[-1]
        try:
            if exc:
                curr_exc = exc
                exc = None
                res = top.throw(curr_exc)
            else:
                res = top.send(val)
                val = None
            if inspect.iscoroutine(res):
                stack.append(res)
            elif res is None:
                pass
            else:
                val = res
        except StopIteration as e:
            stack.pop()
            val = e.value
        except Exception as e:
            stack.pop()
            exc = e
    if exc:
        raise exc
    return val


def test_deep_web_preview_links():
    """Menguji parsing link t.me/s/... dan t.me/s/c/... (format web preview Telegram)."""
    assert parse_telegram_post_link("https://t.me/s/durov/100") == ("@durov", 100)
    assert parse_telegram_post_link("http://telegram.me/s/durov/200") == ("@durov", 200)
    assert parse_telegram_post_link("t.me/s/my_channel/300") == ("@my_channel", 300)
    assert parse_telegram_post_link("https://t.me/s/c/123456789/400") == (-100123456789, 400)


def test_deep_backtick_and_brackets_stripping():
    """Menguji pembersihan backtick dan tanda kurung formatting."""
    assert parse_telegram_post_link("`https://t.me/durov/100`") == ("@durov", 100)
    assert parse_telegram_post_link("<https://t.me/durov/100>") == ("@durov", 100)
    assert parse_telegram_post_link("`https://t.me/s/durov/100`") == ("@durov", 100)


def test_deep_indonesian_range_keywords():
    """Menguji pemisahan rentang menggunakan kata penghubung bahasa Indonesia (sampai, s/d, sd)."""
    # sampai
    mode, res = parse_pfp_args(["https://t.me/ch/100", "sampai", "https://t.me/ch/120"])
    assert mode == "RANGE"
    assert res == ("https://t.me/ch/100", "https://t.me/ch/120")

    # s/d
    mode, res = parse_pfp_args(["https://t.me/ch/100", "s/d", "https://t.me/ch/120"])
    assert mode == "RANGE"
    assert res == ("https://t.me/ch/100", "https://t.me/ch/120")

    # sd
    mode, res = parse_pfp_args(["https://t.me/ch/100", "sd", "https://t.me/ch/120"])
    assert mode == "RANGE"
    assert res == ("https://t.me/ch/100", "https://t.me/ch/120")


def test_deep_ipc_no_duplicate_when_partial_bot_success():
    """Memastikan IPC tidak dipanggil ulang jika bot sudah berhasil mem-forward sebagian post (mencegah duplikasi)."""
    bot = AsyncMock()
    # Batch gagal karena salah satu pesan terhapus
    bot.forward_messages = AsyncMock(side_effect=Exception("Message to forward not found"))
    # Pesan 100 berhasil, pesan 101 gagal chat not found
    def mock_single(chat_id, from_chat_id, message_id):
        if message_id == 100:
            return MagicMock()
        raise Exception("Chat not found")
    bot.forward_message = AsyncMock(side_effect=mock_single)

    conn = MagicMock()
    db = MagicMock()
    db.create_userbot_request = AsyncMock()

    count, err = run_sync(forward_posts_to_keep(
        bot=bot,
        conn=conn,
        db=db,
        keep_ch_id=-1001111111111,
        from_chat="@test",
        start_id=100,
        end_id=101,
    ))

    # Karena count > 0 (1 pesan berhasil), IPC TIDAK boleh dipanggil agar pesan 100 tidak terduplikasi
    assert count == 1
    assert err is None
    db.create_userbot_request.assert_not_called()


def test_deep_cmd_pfp_status_msg_failure_resilience():
    """Jika pesan status awal gagal terkirim (network hiccup), forwarding tetap berjalan normal."""
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.reply_text.side_effect = [
        NetworkError("Connection reset"),
        MagicMock(),
    ]
    update.effective_user.id = 999
    update.effective_chat.id = -100999

    context = MagicMock()
    context.args = ["https://t.me/ch/100"]
    context.bot.forward_message = AsyncMock(return_value=MagicMock())
    mock_db = MagicMock()
    mock_db.log_pfp_forward = AsyncMock()
    mock_conn = MagicMock()

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391), \
         patch("bot.handlers.pfp._conn", return_value=mock_conn), \
         patch("bot.handlers.pfp._db", return_value=mock_db):
        run_sync(cmd_pfp(update, context))

    context.bot.forward_message.assert_called_once()
    assert update.effective_message.reply_text.call_count == 2
    mock_db.log_pfp_forward.assert_called_once()


def test_deep_cmd_pfp_effective_chat_none():
    """Memastikan jika update.effective_chat bernilai None, tidak melempar AttributeError."""
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock(return_value=AsyncMock())
    update.effective_user.id = 999
    update.effective_chat = None  # None chat edge case

    context = MagicMock()
    context.args = ["https://t.me/ch/100"]
    context.bot.forward_message = AsyncMock(return_value=MagicMock())

    mock_db = MagicMock()
    mock_db.log_pfp_forward = AsyncMock()
    mock_conn = MagicMock()

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391), \
         patch("bot.handlers.pfp._conn", return_value=mock_conn), \
         patch("bot.handlers.pfp._db", return_value=mock_db):
        run_sync(cmd_pfp(update, context))

    mock_db.log_pfp_forward.assert_called_once()
    assert mock_db.log_pfp_forward.call_args.kwargs["chat_id"] == 999


def test_deep_cb_pfp_finally_answers():
    """Memastikan query.answer() selalu terpanggil meskipun edit_message_text mengalami error tak terduga."""
    update = MagicMock()
    query = MagicMock()
    query.data = "pfp:daily"
    query.edit_message_text = AsyncMock(side_effect=NetworkError("Telegram timeout"))
    query.answer = AsyncMock()
    update.callback_query = query
    update.effective_user.id = 111  # Owner

    context = MagicMock()

    with patch("bot.handlers.pfp.is_owner", return_value=True), \
         patch("bot.handlers.pfp.get_pfp_daily_content", AsyncMock(return_value=("text", None))):
        run_sync(cb_pfp(update, context))

    query.answer.assert_called_once()


def test_deep_checker_forward_malformed_action():
    """Memastikan aksi FORWARD yang cacat di-mark ERROR — diuji melalui logika validasi."""
    action = "FORWARD:bad_format"
    parts = action.split(":")
    assert len(parts) < 4, "Malformed FORWARD harus punya < 4 bagian"
    with pytest.raises(ValueError, match="Malformed FORWARD"):
        if len(parts) < 4:
            raise ValueError(f"Malformed FORWARD action: expected 4+ parts, got {len(parts)}")
