import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import BadRequest, NetworkError

from bot.handlers.pfp import (
    parse_telegram_post_link,
    parse_pfp_args,
    forward_posts_to_keep,
    cmd_pfp,
    cb_pfp,
)
from checker import process_userbot_requests


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


@pytest.mark.asyncio
async def test_deep_ipc_no_duplicate_when_partial_bot_success():
    """Memastikan IPC tidak dipanggil ulang jika bot sudah berhasil mem-forward sebagian post (mencegah duplikasi)."""
    bot = AsyncMock()
    # Batch gagal karena salah satu pesan terhapus
    bot.forward_messages.side_effect = Exception("Message to forward not found")
    # Pesan 100 berhasil, pesan 101 gagal chat not found
    async def mock_single(chat_id, from_chat_id, message_id):
        if message_id == 100:
            return MagicMock()
        raise Exception("Chat not found")
    bot.forward_message.side_effect = mock_single

    conn = MagicMock()
    db = MagicMock()
    db.create_userbot_request = AsyncMock()

    count, err = await forward_posts_to_keep(
        bot=bot,
        conn=conn,
        db=db,
        keep_ch_id=-1001111111111,
        from_chat="@test",
        start_id=100,
        end_id=101,
    )

    # Karena count > 0 (1 pesan berhasil), IPC TIDAK boleh dipanggil agar pesan 100 tidak terduplikasi
    assert count == 1
    assert err is None
    db.create_userbot_request.assert_not_called()


@pytest.mark.asyncio
async def test_deep_cmd_pfp_status_msg_failure_resilience():
    """Jika pesan status awal gagal terkirim (network hiccup), forwarding tetap berjalan normal."""
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    # Panggilan pertama kirim status_msg gagal, panggilan kedua (hasil akhir) berhasil
    update.effective_message.reply_text.side_effect = [
        NetworkError("Connection reset"),
        MagicMock(),
    ]
    update.effective_user.id = 999
    update.effective_chat.id = -100999

    context = MagicMock()
    context.args = ["https://t.me/ch/100"]
    context.bot.forward_message = AsyncMock(return_value=MagicMock())

    with patch("bot.handlers.pfp.is_owner", return_value=False), \
         patch("bot.handlers.pfp.KEEP_CH_ID", -1004387877391):
        await cmd_pfp(update, context)

    # Memastikan forward tetap dieksekusi dan hasil akhir tetap dikirimkan ke chat
    context.bot.forward_message.assert_called_once()
    assert update.effective_message.reply_text.call_count == 2


@pytest.mark.asyncio
async def test_deep_cmd_pfp_effective_chat_none():
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
        await cmd_pfp(update, context)

    mock_db.log_pfp_forward.assert_called_once()
    # Pastikan fallback chat_id menggunakan user_id (999)
    assert mock_db.log_pfp_forward.call_args.kwargs["chat_id"] == 999


@pytest.mark.asyncio
async def test_deep_cb_pfp_finally_answers():
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
        await cb_pfp(update, context)

    # Spinner loading tombol harus tetap di-dismiss
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_deep_checker_forward_malformed_action():
    """Memastikan aksi FORWARD yang cacat di checker.py di-update menjadi ERROR dan tidak macet di PENDING."""
    conn = MagicMock()
    row = {
        "id": 12,
        "chat_id": "0",
        "action": "FORWARD:bad_format",  # Kurang dari 4 bagian
        "created_at": 100000.0,
    }
    cur = MagicMock()
    cur.fetchall = AsyncMock(return_value=[row])
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()

    with patch("time.time", return_value=100005.0):
        await process_userbot_requests(conn)

    # Memastikan dieksekusi UPDATE status = 'ERROR'
    calls = conn.execute.call_args_list
    error_update_found = any(
        "UPDATE userbot_requests SET status = 'ERROR'" in c[0][0] for c in calls
    )
    assert error_update_found
