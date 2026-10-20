import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import ROLE_INTERNAL, ROLE_STUDENT, ROLE_OWNER, ROLE_ADMIN, ROLE_BEM
from bot.handlers.common import (
    is_acharyata_profile,
    presence_allowed_class_ids,
)
from bot.handlers.attendance import cmd_tutup_presensi
from bot.handlers.commands import cmd_kick


def test_acharyata_profile_and_presence_scope():
    # 1. Acharyata via position_detail
    prof_acharyata = {"position_detail": ["d_pembina"], "full_name": "Pembina 1"}
    assert is_acharyata_profile(prof_acharyata) is True
    allowed_acharyata = presence_allowed_class_ids(ROLE_INTERNAL, prof_acharyata)
    assert allowed_acharyata is not None
    assert "bem_manual" in allowed_acharyata
    assert "event_bebas" in allowed_acharyata

    # 2. Acharyata via position field
    prof_acharyata_pos = {"position": "pembina", "full_name": "Pembina 2"}
    assert is_acharyata_profile(prof_acharyata_pos) is True
    allowed_pos = presence_allowed_class_ids(ROLE_INTERNAL, prof_acharyata_pos)
    assert allowed_pos is not None
    assert "bem_manual" in allowed_pos

    # 3. Regular student should not have bem_manual
    prof_student = {"major": "sm", "full_name": "Student 1"}
    assert is_acharyata_profile(prof_student) is False
    allowed_student = presence_allowed_class_ids(ROLE_STUDENT, prof_student)
    assert allowed_student is not None
    assert "bem_manual" not in allowed_student
    assert "event_bebas" in allowed_student

    # 4. BEM role should have bem_manual
    prof_bem = {"bem_position": "bem_ketua"}
    allowed_bem = presence_allowed_class_ids(ROLE_BEM, prof_bem)
    assert allowed_bem is not None
    assert "bem_manual" in allowed_bem


@pytest.mark.asyncio
async def test_strict_tutup_presensi_umum():
    # Setup mock objects
    update = MagicMock(spec=Update)
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    message = AsyncMock(spec=Message)
    user = MagicMock(spec=User)

    update.effective_user = user
    update.message = message

    # Mock DB and connection
    db = MagicMock()
    conn = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()

    # Case 1: Session is event_bebas, opened by user 1001. User 2002 (student) tries to close it.
    user.id = 2002
    context.args = ["50"]
    sess = {
        "id": 50,
        "class_id": "event_bebas",
        "title": "Presensi Umum",
        "opened_by": 1001,
        "closed_at": None,
        "opened_at": 1700000000.0,
        "announce_message_id": None,
        "chat_id": -100,
    }
    user_row = {"telegram_id": 2002, "role": ROLE_STUDENT, "profile_json": "{}"}

    db.get_user = AsyncMock(return_value=user_row)
    db.get_attendance_session = AsyncMock(return_value=sess)

    await cmd_tutup_presensi(update, context)

    # Must be rejected because user 2002 did not open the session and is not admin/owner
    message.reply_text.assert_called_with(
        "Hanya pembuat sesi atau Admin/Owner yang dapat menutup presensi umum ini."
    )
    assert not db.close_attendance_session.called

    # Case 2: Opener (user 1001) closes their own event_bebas session
    message.reply_text.reset_mock()
    user.id = 1001
    opener_row = {"telegram_id": 1001, "role": ROLE_STUDENT, "profile_json": "{}"}
    db.get_user = AsyncMock(return_value=opener_row)
    db.close_attendance_session = AsyncMock()
    db.add_audit = AsyncMock()
    db.attendance_recap_session = AsyncMock(return_value=(sess, []))
    db.list_moderator_telegram_ids = AsyncMock(return_value=[])

    await cmd_tutup_presensi(update, context)
    db.close_attendance_session.assert_called_once_with(conn, 50)
    message.reply_text.assert_called_with("Sesi <code>50</code> ditutup.")

    # Case 3: Admin/Owner closes user 1001's event_bebas session
    message.reply_text.reset_mock()
    db.close_attendance_session.reset_mock()
    user.id = 9999
    admin_row = {"telegram_id": 9999, "role": ROLE_ADMIN, "profile_json": "{}"}
    db.get_user = AsyncMock(return_value=admin_row)

    await cmd_tutup_presensi(update, context)
    db.close_attendance_session.assert_called_once_with(conn, 50)
    message.reply_text.assert_called_with("Sesi <code>50</code> ditutup.")


@pytest.mark.asyncio
async def test_cmd_kick_pm_only_shows_target_groups():
    update = MagicMock(spec=Update)
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    message = AsyncMock(spec=Message)
    user = MagicMock(spec=User)
    chat = MagicMock(spec=Chat)

    user.id = 9000  # Owner / Admin / Sekre
    user.first_name = "Sekre"
    chat.type = "private"
    chat.id = 9000
    message.text = "/kick 3001"
    message.reply_to_message = None

    update.effective_user = user
    update.effective_chat = chat
    update.message = message

    db = MagicMock()
    conn = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    caller_row = {
        "telegram_id": 9000,
        "role": ROLE_INTERNAL,
        "profile_json": '{"position_detail": ["d_sekre"]}',
    }
    target_row = {
        "telegram_id": 3001,
        "first_name": "TargetUser",
        "role": ROLE_STUDENT,
        "profile_json": "{}",
    }

    db.get_user = AsyncMock(side_effect=lambda c, uid: caller_row if uid == 9000 else (target_row if uid == 3001 else None))
    db.get_user_by_username_or_id = AsyncMock(return_value=target_row)

    # 3 active bot chats
    db.list_active_bot_chats = AsyncMock(return_value=[
        (-1001, "Grup 1"),
        (-1002, "Grup 2"),
        (-1003, "Grup 3"),
    ])

    # Target is only a member of Grup 2 (-1002).
    # In Grup 1: raises exception / not found
    # In Grup 2: status == "member"
    # In Grup 3: status == "left"
    async def mock_get_chat_member(chat_id, user_id):
        if chat_id == -1002:
            m = MagicMock()
            m.status = "member"
            return m
        elif chat_id == -1003:
            m = MagicMock()
            m.status = "left"
            return m
        else:
            raise Exception("User not found")

    context.bot.get_chat_member = AsyncMock(side_effect=mock_get_chat_member)

    await cmd_kick(update, context)

    # Verify message sent has reply_markup with ONLY Grup 2
    message.reply_text.assert_called_once()
    _, kwargs = message.reply_text.call_args
    reply_markup = kwargs.get("reply_markup")
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    buttons = reply_markup.inline_keyboard
    # Expected: [ [Grup 2 button], [Batal button] ]
    assert len(buttons) == 2
    assert buttons[0][0].text == "Grup 2"
    assert buttons[0][0].callback_data == "kick:-1002:3001"
    assert buttons[1][0].text == "Batal"


@pytest.mark.asyncio
async def test_on_kick_callback_auth_and_cancel():
    from bot.handlers.commands import on_kick_callback

    update = MagicMock(spec=Update)
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    query = AsyncMock()
    user = MagicMock(spec=User)

    update.callback_query = query
    query.from_user = user

    db = MagicMock()
    conn = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    # Case 1: Cancel callback
    query.data = "kick:cancel:0"
    await on_kick_callback(update, context)
    query.edit_message_text.assert_called_with("❌ Dibatalkan.")

    # Case 2: Unauthorized user tries to click kick button
    query.data = "kick:-1002:3001"
    user.id = 5555  # Regular student
    student_row = {"telegram_id": 5555, "role": ROLE_STUDENT, "profile_json": "{}"}
    db.get_user = AsyncMock(return_value=student_row)

    await on_kick_callback(update, context)
    query.edit_message_text.assert_called_with(
        "⛔ Anda tidak memiliki izin untuk melakukan tindakan ini."
    )

    # Case 3: Authorized sekre clicks kick button
    user.id = 9000
    sekre_row = {
        "telegram_id": 9000,
        "role": ROLE_INTERNAL,
        "profile_json": '{"position_detail": ["d_sekre"]}',
    }
    target_row = {
        "telegram_id": 3001,
        "first_name": "TargetUser",
        "role": ROLE_STUDENT,
        "profile_json": "{}",
    }
    db.get_user = AsyncMock(side_effect=lambda c, uid: sekre_row if uid == 9000 else target_row)
    context.bot.ban_chat_member = AsyncMock()
    context.bot.unban_chat_member = AsyncMock()
    update.effective_user = user
    update.effective_message = AsyncMock()

    await on_kick_callback(update, context)
    context.bot.ban_chat_member.assert_called_once_with(chat_id=-1002, user_id=3001)
    context.bot.unban_chat_member.assert_called_once_with(chat_id=-1002, user_id=3001)


@pytest.mark.asyncio
async def test_acharyata_can_attend_and_rekap_yaksa():
    from bot.handlers.attendance import cmd_rekap_hadir, _record_hadir, classes_for_presensi
    from bot.handlers.common import is_acharyata_profile

    db = MagicMock()
    conn = MagicMock()

    # Acharyata profile
    acharyata_prof = {
        "position_detail": ["d_pembina"],
        "full_name": "Pembina BEM",
    }
    assert is_acharyata_profile(acharyata_prof) is True

    # Check classes_for_presensi includes bem_manual when handling attend
    user_classes = classes_for_presensi(acharyata_prof, ROLE_INTERNAL)
    if is_acharyata_profile(acharyata_prof):
        user_classes.append("bem_manual")
    assert "bem_manual" in user_classes

    # Simulate _record_hadir
    sess_yaksa = {
        "id": 88,
        "class_id": "bem_manual",
        "opened_by": 9000,
        "closed_at": None,
        "opened_at": 1700000000.0,
    }
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=sess_yaksa)
    conn.execute = AsyncMock(return_value=cur)
    db.record_attendance = AsyncMock(return_value=(True, None))
    db.add_agra = AsyncMock()

    ok, msg, _ = await _record_hadir(
        db, conn, 88, 7777, ROLE_INTERNAL, user_classes, status="hadir"
    )
    assert ok is True
    assert "tercatat sebagai Hadir" in msg

    # Check cmd_rekap_hadir
    update = MagicMock(spec=Update)
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    message = AsyncMock(spec=Message)
    user = MagicMock(spec=User)

    user.id = 7777
    update.effective_user = user
    update.message = message
    context.application.bot_data = {"conn": conn, "db": db}
    context.args = ["88"]

    acharyata_row = {
        "telegram_id": 7777,
        "role": ROLE_INTERNAL,
        "profile_json": '{"position_detail": ["d_pembina"], "full_name": "Pembina BEM"}',
    }
    db.get_user = AsyncMock(return_value=acharyata_row)
    db.attendance_recap_session = AsyncMock(return_value=(sess_yaksa, []))

    await cmd_rekap_hadir(update, context)
    message.reply_text.assert_called_once()
    recap_text = message.reply_text.call_args[0][0]
    assert "Rekap presensi" in recap_text
    assert "Presensi Yaksa" in recap_text

