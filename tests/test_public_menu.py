import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import InlineKeyboardMarkup
from bot.database import Database
from bot.handlers import commands
from tests.test_warkat import AsyncSqliteMockConn, run_sync
import sqlite3

@pytest.fixture
def test_db():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.execute(
        """CREATE TABLE users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            role TEXT DEFAULT 'public',
            onboarding_step TEXT,
            profile_json TEXT,
            created_at REAL,
            updated_at REAL
        )"""
    )
    raw.execute(
        """CREATE TABLE bot_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )"""
    )
    raw.execute(
        """CREATE TABLE access_codes (
            code TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            used_by INTEGER,
            used_at REAL,
            target_role TEXT NOT NULL DEFAULT 'student'
        )"""
    )
    raw.execute(
        """CREATE TABLE warkat_codes (
            code TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            created_by INTEGER NOT NULL,
            expires_charya REAL NOT NULL,
            created_gen INTEGER NOT NULL DEFAULT 1,
            max_generasi INTEGER NOT NULL,
            used_by INTEGER,
            used_at REAL,
            chosen_track TEXT,
            charya_div_1 TEXT,
            charya_div_2 TEXT,
            charya_div_3 TEXT
        )"""
    )
    conn = AsyncSqliteMockConn(raw)
    db = Database(path=":memory:")
    return db, conn, raw

def test_public_contact_and_back_buttons(test_db):
    db, conn, raw = test_db
    user_id = 12345
    raw.execute(
        "INSERT INTO users (telegram_id, username, first_name, role) VALUES (?, ?, ?, ?)",
        (user_id, "guest", "Guest", "public")
    )
    raw.commit()

    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    def make_callback_update(data):
        user = MagicMock(id=user_id, username="guest")
        q = MagicMock()
        q.data = data
        q.from_user = user
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        up = MagicMock(callback_query=q)
        return up, q

    # 1. Click pub:hubungi
    up_hub, q_hub = make_callback_update("pub:hubungi")
    run_sync(commands.on_callback(up_hub, context))
    assert q_hub.edit_message_text.called
    hub_text, hub_kwargs = q_hub.edit_message_text.call_args[0][0], q_hub.edit_message_text.call_args[1]
    assert "Pilih instansi yang ingin Anda hubungi:" in hub_text
    km_hub = hub_kwargs["reply_markup"]
    # Check order of buttons
    btn_labels = [row[0].text for row in km_hub.inline_keyboard]
    btn_datas = [row[0].callback_data for row in km_hub.inline_keyboard]
    assert "Kirim undangan acara." in btn_labels[0]
    assert btn_datas[0] == "pub:undangan"
    assert "Seputar kemitraan" in btn_labels[1]
    assert btn_datas[1] == "pub:medpart"
    assert "⬅️ Kembali" in btn_labels[-1]
    assert btn_datas[-1] == "pub:back"

    # 2. Click pub:undangan -> @dhruvaekagrabot + Back button to pub:hubungi
    up_und, q_und = make_callback_update("pub:undangan")
    run_sync(commands.on_callback(up_und, context))
    und_text = q_und.edit_message_text.call_args[0][0]
    und_km = q_und.edit_message_text.call_args[1]["reply_markup"]
    assert "@dhruvaekagrabot" in und_text
    assert und_km.inline_keyboard[0][0].callback_data == "pub:hubungi"

    # 3. Click pub:medpart -> @dhruvamitrabot + Back button to pub:hubungi
    up_med, q_med = make_callback_update("pub:medpart")
    run_sync(commands.on_callback(up_med, context))
    med_text = q_med.edit_message_text.call_args[0][0]
    med_km = q_med.edit_message_text.call_args[1]["reply_markup"]
    assert "@dhruvamitrabot" in med_text
    assert med_km.inline_keyboard[0][0].callback_data == "pub:hubungi"

    # 4. Click pub:hrd -> @HRDhruvabot + Back button to pub:hubungi
    up_hrd, q_hrd = make_callback_update("pub:hrd")
    run_sync(commands.on_callback(up_hrd, context))
    hrd_text = q_hrd.edit_message_text.call_args[0][0]
    hrd_km = q_hrd.edit_message_text.call_args[1]["reply_markup"]
    assert "@HRDhruvabot" in hrd_text
    assert hrd_km.inline_keyboard[0][0].callback_data == "pub:hubungi"

    # 5. Click pub:akademik -> @acadhruvabot + Back button to pub:hubungi
    up_aka, q_aka = make_callback_update("pub:akademik")
    run_sync(commands.on_callback(up_aka, context))
    aka_text = q_aka.edit_message_text.call_args[0][0]
    aka_km = q_aka.edit_message_text.call_args[1]["reply_markup"]
    assert "@acadhruvabot" in aka_text
    assert aka_km.inline_keyboard[0][0].callback_data == "pub:hubungi"

    # 6. Click pub:lainnya -> Back button to pub:back
    up_lai, q_lai = make_callback_update("pub:lainnya")
    run_sync(commands.on_callback(up_lai, context))
    lai_km = q_lai.edit_message_text.call_args[1]["reply_markup"]
    assert lai_km.inline_keyboard[0][0].callback_data == "pub:back"

    # 7. Click pub:kode -> sets INPUT_CODE + Back button to pub:back
    up_kod, q_kod = make_callback_update("pub:kode")
    run_sync(commands.on_callback(up_kod, context))
    kod_km = q_kod.edit_message_text.call_args[1]["reply_markup"]
    assert kod_km.inline_keyboard[0][0].callback_data == "pub:back"
    u_after_kode = run_sync(db.get_user(conn, user_id))
    assert u_after_kode["onboarding_step"] == "INPUT_CODE"

    # 8. Click pub:back -> clears INPUT_CODE and renders main public menu
    up_bak, q_bak = make_callback_update("pub:back")
    run_sync(commands.on_callback(up_bak, context))
    u_after_back = run_sync(db.get_user(conn, user_id))
    assert u_after_back["onboarding_step"] is None
    bak_text = q_bak.edit_message_text.call_args[0][0]
    bak_km = q_bak.edit_message_text.call_args[1]["reply_markup"]
    assert "Selamat datang!" in bak_text
    back_datas = [row[0].callback_data for row in bak_km.inline_keyboard]
    assert "pub:kode" in back_datas
    assert "pub:hubungi" in back_datas
    assert "pub:lainnya" in back_datas


def test_gencode_menu_and_callbacks(test_db):
    from unittest.mock import patch
    db, conn, raw = test_db
    owner_id = 99999

    context = MagicMock()
    context.application.bot_data = {"conn": conn, "db": db}

    def make_msg_update(uid, text, args=None):
        user = MagicMock(id=uid, username="test_user")
        message = MagicMock()
        message.text = text
        message.reply_text = AsyncMock()
        update = MagicMock(effective_user=user, message=message)
        ctx = MagicMock(args=args if args is not None else (text.split()[1:] if len(text.split()) > 1 else []))
        ctx.application.bot_data = {"conn": conn, "db": db}
        return update, ctx, message

    def make_cb_update(uid, data):
        user = MagicMock(id=uid, username="test_user")
        q = MagicMock()
        q.data = data
        q.from_user = user
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        up = MagicMock(callback_query=q)
        return up, q

    # 1. Non-owner blocked from /gencode
    up_non, ctx_non, msg_non = make_msg_update(11111, "/gencode")
    with patch("bot.handlers.commands.is_owner", return_value=False):
        run_sync(commands.cmd_gencode(up_non, ctx_non))
    assert "Tidak diizinkan" in msg_non.reply_text.call_args[0][0]

    # 2. Owner calls /gencode without args -> shows Sub Menu
    up_owner, ctx_owner, msg_owner = make_msg_update(owner_id, "/gencode", args=[])
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(commands.cmd_gencode(up_owner, ctx_owner))
    menu_text = msg_owner.reply_text.call_args[0][0]
    menu_km = msg_owner.reply_text.call_args[1]["reply_markup"]
    assert "Manajemen Kode Akses & Warkat Kehormatan" in menu_text
    assert "Kode Akses Standar Tersedia: <b>0</b>" in menu_text
    assert "Warkat Kehormatan Tersedia: <b>0</b>" in menu_text
    assert "/gencode_warkat" in menu_text
    cb_datas = [row[0].callback_data for row in menu_km.inline_keyboard]
    assert "gencode:avail_std" in cb_datas
    assert "gencode:avail_wkt" in cb_datas

    # 3. Click gencode:avail_std (when empty)
    up_cb_std, q_cb_std = make_cb_update(owner_id, "gencode:avail_std")
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(commands.on_callback(up_cb_std, context))
    std_text = q_cb_std.edit_message_text.call_args[0][0]
    std_km = q_cb_std.edit_message_text.call_args[1]["reply_markup"]
    assert "Tidak ada kode akses standar yang tersedia" in std_text
    assert std_km.inline_keyboard[0][0].callback_data == "gencode:menu"

    # 4. Generate 2 codes with role bem using /gencode 2 bem
    up_gen, ctx_gen, msg_gen = make_msg_update(owner_id, "/gencode 2 bem", args=["2", "bem"])
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(commands.cmd_gencode(up_gen, ctx_gen))
    gen_text = msg_gen.reply_text.call_args[0][0]
    assert "Berhasil generate 2 kode akses" in gen_text
    assert "Role: bem" in gen_text

    # 5. Click gencode:avail_std again (now has 2 codes)
    q_cb_std.edit_message_text.reset_mock()
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(commands.on_callback(up_cb_std, context))
    std_text2 = q_cb_std.edit_message_text.call_args[0][0]
    assert "Terdapat 2 Kode Akses Standar Belum Diklaim" in std_text2
    assert "Role: <code>bem</code>" in std_text2

    # 6. Click gencode:menu -> returns to main gencode menu
    up_cb_menu, q_cb_menu = make_cb_update(owner_id, "gencode:menu")
    with patch("bot.handlers.commands.is_owner", return_value=True):
        run_sync(commands.on_callback(up_cb_menu, context))
    menu_back_text = q_cb_menu.edit_message_text.call_args[0][0]
    assert "Kode Akses Standar Tersedia: <b>2</b>" in menu_back_text

