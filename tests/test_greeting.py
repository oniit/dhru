import html
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Chat, Message, ChatMember

from bot.database import ROLE_OWNER, ROLE_ADMIN, ROLE_STUDENT
import bot.settings
from bot.handlers.common import (
    render_greeting_message,
    sanitize_telegram_html,
    validate_greeting_html,
)
from bot.handlers import commands
from bot.handlers import messages


def run_sync(coro):
    """Drive pure async coroutines that only await AsyncMocks without asyncio event loop sockets."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


class DummyUser:
    def __init__(self, uid=12345678, first_name="Budi", last_name="Santoso", username="budisantoso"):
        self.id = uid
        self.first_name = first_name
        self.last_name = last_name
        self.full_name = f"{first_name} {last_name}".strip()
        self.username = username


def make_context():
    context = MagicMock()
    mock_db = MagicMock()
    mock_db.get_user = AsyncMock(return_value={"telegram_id": 999, "role": ROLE_OWNER})
    mock_db.list_active_bot_chats = AsyncMock(return_value=[(-10011111, "Grup Alpha"), (-10022222, "Grup Beta")])
    mock_db.get_bot_chat = AsyncMock(return_value={"chat_id": -10055555, "title": "Grup Keren", "greeting_message": None})
    mock_db.update_greeting_message = AsyncMock()
    context.application.bot_data = {"conn": MagicMock(), "db": mock_db}
    return context, mock_db


def test_render_greeting_message_all_placeholders():
    user = DummyUser(uid=98765432, first_name="Ahmad", last_name="Dahlan", username="ahmad_d")
    template = (
        "Halo {name} / {full_name}!\n"
        "Nama depan: {first_name}, belakang: {last_name}.\n"
        "User: {username}, ID: {id} / {user_id}.\n"
        "Tag: {mention}.\n"
        "Grup: {chat_title} / {title}."
    )
    rendered = render_greeting_message(template, user, chat_title="Grup Seru")
    assert "Halo Ahmad Dahlan / Ahmad Dahlan!" in rendered
    assert "Nama depan: Ahmad, belakang: Dahlan." in rendered
    assert "User: @ahmad_d, ID: 98765432 / 98765432." in rendered
    assert '<a href="tg://user?id=98765432">Ahmad Dahlan</a>' in rendered
    assert "Grup: Grup Seru / Grup Seru." in rendered


def test_render_greeting_message_no_username():
    user = DummyUser(uid=112233, first_name="Siti", last_name="", username=None)
    template = "Halo {name} ({username}), ID: {id}"
    rendered = render_greeting_message(template, user, chat_title="Komunitas")
    assert "Halo Siti (Siti), ID: 112233" in rendered


def test_render_greeting_message_escapes_xss_in_user_data():
    user = DummyUser(uid=123, first_name="<script>alert(1)</script>", last_name="&co", username="hacker<tag>")
    template = "Halo <b>{name}</b> ({username}) di <b>{chat_title}</b>"
    rendered = render_greeting_message(template, user, chat_title="Grup <Utama>")
    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "@hacker&lt;tag&gt;" in rendered
    assert "Grup &lt;Utama&gt;" in rendered
    assert "<b>" in rendered and "</b>" in rendered


def test_sanitize_telegram_html():
    text1 = "Halo & selamat datang &amp; nikmati kopi &lt;3"
    sanitized1 = sanitize_telegram_html(text1)
    assert sanitized1 == "Halo &amp; selamat datang &amp; nikmati kopi &lt;3"

    text2 = "Code &#123; and &#x7b; & test"
    sanitized2 = sanitize_telegram_html(text2)
    assert sanitized2 == "Code &#123; and &#x7b; &amp; test"


def test_validate_greeting_html():
    ok1, err1 = validate_greeting_html("Halo <b>{name}</b>, selamat datang di <a href=\"https://t.me\">grup</a>!")
    assert ok1 is True
    assert err1 is None

    ok2, err2 = validate_greeting_html("Halo <b>{name}")
    assert ok2 is False
    assert "belum ditutup" in err2

    ok3, err3 = validate_greeting_html("Halo <marquee>{name}</marquee>")
    assert ok3 is False
    assert "tidak didukung" in err3

    ok4, err4 = validate_greeting_html("Halo <a>klik</a>")
    assert ok4 is False
    assert "href" in err4

    ok5, err5 = validate_greeting_html("Halo <b>{name}</b> <3")
    assert ok5 is False
    assert "Terdapat karakter" in err5


def test_render_greeting_message_single_pass_no_cascade():
    # User whose name contains a placeholder must not be re-expanded
    user = DummyUser(uid=123, first_name="Budi {chat_title}", last_name="", username="budi")
    rendered = render_greeting_message("Halo {first_name} di {chat_title}!", user, chat_title="Grup Keren")
    assert "Halo Budi {chat_title} di Grup Keren!" in rendered


def test_render_greeting_message_handles_at_username():
    user_with_uname = DummyUser(uid=1, first_name="Budi", last_name="", username="budis")
    assert render_greeting_message("Halo @{username}!", user_with_uname) == "Halo @budis!"
    assert render_greeting_message("Halo {username}!", user_with_uname) == "Halo @budis!"

    user_without_uname = DummyUser(uid=2, first_name="Siti", last_name="Rahma", username=None)
    assert render_greeting_message("Halo @{username}!", user_without_uname) == "Halo Siti Rahma!"
    assert render_greeting_message("Halo {username}!", user_without_uname) == "Halo Siti Rahma!"


def test_cmd_set_greeting_preserves_native_telegram_formatting():
    from telegram import MessageEntity
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Owner")
    update.effective_chat = MagicMock(id=-10055555, type="supergroup", title="Grup Keren")
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    # Simulated native bold: user typed /setgreeting Halo {name} and bolded {name}
    update.message.text = "/setgreeting Halo {name}!"
    update.message.text_html = "/setgreeting Halo <b>{name}</b>!"
    update.message.entities = [
        MessageEntity(MessageEntity.BOT_COMMAND, 0, 12),
        MessageEntity(MessageEntity.BOLD, 18, 6)
    ]

    context, mock_db = make_context()
    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_called_once()
    saved_template = mock_db.update_greeting_message.call_args[0][2]
    assert "Halo <b>{name}</b>!" in saved_template


def test_cmd_set_greeting_help_in_group_does_not_leak_other_groups():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Owner")
    update.effective_chat = MagicMock(id=-10055555, type="supergroup", title="Grup Publik")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting help"
    update.message.entities = []

    context, mock_db = make_context()
    run_sync(commands.cmd_set_greeting(update, context))

    reply = update.message.reply_text.call_args[0][0]
    assert "Grup Publik" in reply
    assert "-10055555" in reply
    # Must NOT leak external bot chats in group chat!
    assert "Grup Alpha" not in reply
    assert "-10011111" not in reply


def test_cmd_set_greeting_negative_number_not_treated_as_chat_id():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Owner")
    update.effective_chat = MagicMock(id=-10055555, type="supergroup", title="Grup Keren")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting -10 poin jika melanggar!"
    update.message.text_html = "/setgreeting -10 poin jika melanggar!"
    update.message.entities = []

    context, mock_db = make_context()
    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_called_once()
    # Target chat must remain current group, not -10!
    assert mock_db.update_greeting_message.call_args[0][1] == -10055555
    assert "-10 poin jika melanggar!" in mock_db.update_greeting_message.call_args[0][2]


def test_on_chat_member_ignores_bot():
    from telegram import ChatMemberUpdated
    update = MagicMock(spec=Update)
    update.chat_member = MagicMock(spec=ChatMemberUpdated)
    update.chat_member.chat = MagicMock(id=-1009999, title="Grup Baru")

    old_member = MagicMock(status=ChatMember.LEFT)
    new_member = MagicMock(status=ChatMember.MEMBER)
    new_member.user = DummyUser(uid=888, first_name="Bot Pembantu", last_name="", username="helper_bot")
    new_member.user.is_bot = True
    update.chat_member.old_chat_member = old_member
    update.chat_member.new_chat_member = new_member

    context, mock_db = make_context()
    context.bot.send_message = AsyncMock()

    run_sync(messages.on_chat_member(update, context))

    # Send message should NOT be called for bots
    context.bot.send_message.assert_not_called()


def test_cmd_set_greeting_help_guide():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Admin")
    update.effective_chat = MagicMock(id=999, type="private")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting help"

    context, mock_db = make_context()

    run_sync(commands.cmd_set_greeting(update, context))

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "Panduan Pesan Selamat Datang" in reply
    assert "{mention}" in reply
    assert "Grup Alpha" in reply
    assert "-10011111" in reply


def test_cmd_set_greeting_in_group_success():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=1002, first_name="AdminGroup")
    update.effective_chat = MagicMock(id=-10055555, type="supergroup", title="Grup Keren")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting Halo <b>{mention}</b>, selamat datang di {chat_title}!"

    context, mock_db = make_context()
    mock_db.get_user = AsyncMock(return_value={"telegram_id": 1002, "role": ROLE_STUDENT})
    member_mock = MagicMock(status="administrator")
    context.bot.get_chat_member = AsyncMock(return_value=member_mock)

    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_called_once()
    assert mock_db.update_greeting_message.call_args[0][1] == -10055555
    assert "Halo <b>{mention}</b>" in mock_db.update_greeting_message.call_args[0][2]

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "berhasil diatur untuk grup" in reply
    assert "Grup Keren" in reply


def test_cmd_set_greeting_remote_from_private_chat():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Owner")
    update.effective_chat = MagicMock(id=999, type="private")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting -10077777 Halo {name} di {chat_title}!"

    context, mock_db = make_context()
    mock_db.get_bot_chat = AsyncMock(return_value={"chat_id": -10077777, "title": "Grup Remote"})

    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_called_once()
    assert mock_db.update_greeting_message.call_args[0][1] == -10077777
    assert "Halo {name}" in mock_db.update_greeting_message.call_args[0][2]

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "Grup Remote" in reply
    assert "-10077777" in reply


def test_cmd_set_greeting_remote_off():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=999, first_name="Owner")
    update.effective_chat = MagicMock(id=999, type="private")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting -10077777 off"

    context, mock_db = make_context()
    mock_db.get_bot_chat = AsyncMock(return_value={"chat_id": -10077777, "title": "Grup Remote"})

    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_called_once()
    assert mock_db.update_greeting_message.call_args[0][1] == -10077777
    assert mock_db.update_greeting_message.call_args[0][2] is None
    reply = update.message.reply_text.call_args[0][0]
    assert "dimatikan" in reply


def test_cmd_set_greeting_rejects_unauthorized():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=888, first_name="Stranger")
    update.effective_chat = MagicMock(id=888, type="private")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/setgreeting -10077777 Halo"

    context, mock_db = make_context()
    mock_db.get_user = AsyncMock(return_value={"telegram_id": 888, "role": ROLE_STUDENT})
    member_mock = MagicMock(status="member")
    context.bot.get_chat_member = AsyncMock(return_value=member_mock)

    run_sync(commands.cmd_set_greeting(update, context))

    mock_db.update_greeting_message.assert_not_called()
    reply = update.message.reply_text.call_args[0][0]
    assert "tidak memiliki izin" in reply


def test_cmd_greeting_preview():
    bot.settings.OWNER_ID = 999
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(id=1001, first_name="Alice", last_name="W", username="alice_w")
    update.effective_chat = MagicMock(id=-10088888, type="supergroup", title="Grup Alpha")
    update.message = AsyncMock(spec=Message)
    update.message.text = "/greeting"

    context, mock_db = make_context()
    mock_db.get_user = AsyncMock(return_value={"telegram_id": 1001, "role": ROLE_STUDENT})
    mock_db.get_bot_chat = AsyncMock(return_value={
        "chat_id": -10088888,
        "title": "Grup Alpha",
        "greeting_message": "Selamat datang {name} ({username}) di {chat_title}!"
    })

    run_sync(commands.cmd_greeting(update, context))

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "Pesan selamat datang aktif" in reply
    assert "Alice W (@alice_w) di Grup Alpha" in reply


def test_on_chat_member_updated_sends_greeting():
    from telegram import ChatMemberUpdated
    update = MagicMock(spec=Update)
    update.chat_member = MagicMock(spec=ChatMemberUpdated)
    update.chat_member.chat = MagicMock(id=-1009999, title="Grup Baru")

    old_member = MagicMock(status=ChatMember.LEFT)
    new_member = MagicMock(status=ChatMember.MEMBER)
    new_member.user = DummyUser(uid=777, first_name="Bambang", last_name="Pamungkas", username="bambang9")
    update.chat_member.old_chat_member = old_member
    update.chat_member.new_chat_member = new_member

    context, mock_db = make_context()
    mock_db.get_bot_chat = AsyncMock(return_value={
        "chat_id": -1009999,
        "title": "Grup Baru",
        "greeting_message": "Hai <b>{name}</b> ({username}), selamat datang di <b>{chat_title}</b>!"
    })
    context.bot.send_message = AsyncMock()

    run_sync(messages.on_chat_member(update, context))

    context.bot.send_message.assert_called_once()
    kwargs = context.bot.send_message.call_args[1]
    assert kwargs["chat_id"] == -1009999
    assert kwargs["parse_mode"] == "HTML"
    assert "Hai <b>Bambang Pamungkas</b> (@bambang9), selamat datang di <b>Grup Baru</b>!" in kwargs["text"]

