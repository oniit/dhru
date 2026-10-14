import asyncio
import os
import json
import html
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat, CallbackQuery
from bot.database import Database
from bot.handlers import commands, attendance, triggers, tugas, menfess, common

@pytest.fixture
def mock_app():
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    app.bot.edit_message_text = AsyncMock()
    app.bot_data = {}
    return app

def make_mock_update(user_id=1073487310, text="", is_group=False):
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "Tester"
    user.last_name = "User"
    user.username = "tester"
    update.effective_user = user
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = user_id if not is_group else -10099999
    update.effective_chat.type = "private" if not is_group else "supergroup"
    
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.message_id = 1001
    msg.reply_text = AsyncMock()
    msg.chat_id = update.effective_chat.id
    update.effective_message = msg
    update.message = msg
    return update

@pytest.mark.asyncio
async def test_qa_fix_1_triggers_duplicate_keyword_prevention():
    """Verifikasi: Penambahan trigger dengan keyword yang sudah ada
    akan meng-update action yang ada, bukan membuat baris duplikat."""
    db = Database()
    conn = await db.connect()
    
    kw = "test_qa_kw_duplicate_fix"
    try:
        await conn.execute("DELETE FROM triggers WHERE keyword = ?", (kw,))
        await conn.commit()
    except Exception:
        pass
    
    admin_id = 88000
    await db.upsert_user_from_telegram(conn, telegram_id=admin_id, username="admin_trig", first_name="Admin", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, admin_id, "owner")

    update = make_mock_update(user_id=admin_id, text="/trigger done")
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    
    # 1. Draft pertama
    ctx.user_data = {"trigger_draft": {"keyword": kw, "messages": ["jawaban 1"]}}
    await triggers.cmd_selesai_trigger(update, ctx)
    
    # 2. Draft kedua dengan keyword yang sama
    ctx.user_data = {"trigger_draft": {"keyword": kw, "messages": ["jawaban 2"]}}
    await triggers.cmd_selesai_trigger(update, ctx)
        
    cur = await conn.execute("SELECT id, keyword, actions_json FROM triggers WHERE keyword = ?", (kw,))
    rows = await cur.fetchall()
    
    try:
        # VERIFIKASI: Hanya 1 baris di database dan actions di-update
        assert len(rows) == 1, f"Expected 1 unique trigger row, got {len(rows)}"
        assert json.loads(rows[0]["actions_json"]) == ["jawaban 2"]
    finally:
        try:
            await conn.execute("DELETE FROM triggers WHERE keyword = ?", (kw,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (admin_id,))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_2_tugas_cross_class_idor_blocked():
    """Verifikasi: Mahasiswa dari jurusan lain ditolak saat mencoba mengakses tugas jurusan asing (IDOR fix)."""
    db = Database()
    conn = await db.connect()
    
    dosen_id = 88001
    student_id = 88002 # Mahasiswa Seni Musik (sm), bukan Kimia!
    
    await db.upsert_user_from_telegram(conn, telegram_id=dosen_id, username="dosen_kimia", first_name="Dosen", last_name="Kimia", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, dosen_id, "internal")
    await db.set_profile_partial(conn, dosen_id, {"position_detail": ["d_dosen"], "teaching_classes": ["ik"]})
    
    await db.upsert_user_from_telegram(conn, telegram_id=student_id, username="shishya_musik", first_name="Shishya", last_name="Musik", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, student_id, "student")
    await db.set_profile_partial(conn, student_id, {"major": "sm", "full_name": "Shishya Seni Musik"})
    
    # Dosen membuat tugas matkul Kimia (ik)
    task_id = await db.create_task(conn, class_id="ik", title="Tugas Reaksi Kimia", created_by=dosen_id)
    
    from bot.handlers.tugas import cb_tugas
    update = make_mock_update(user_id=student_id)
    q = MagicMock(spec=CallbackQuery)
    q.data = f"tsi:{task_id}"
    q.from_user = update.effective_user
    q.message = MagicMock(spec=Message)
    q.message.chat_id = student_id
    q.message.edit_text = AsyncMock()
    q.answer = AsyncMock()
    update.callback_query = q
    
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    
    await cb_tugas(update, ctx)
    
    student_row = await db.get_user(conn, student_id)
    step = student_row["onboarding_step"]
    
    try:
        # VERIFIKASI: Akses ditolak, onboarding_step tidak berubah ke TUGAS_INPUT, dan pesan penolakan dikirimkan
        assert step is None or not step.startswith(f"TUGAS_INPUT:{task_id}")
        q.edit_message_text.assert_called_with("Anda tidak terdaftar di kelas/matkul tugas ini.")
    finally:
        try:
            await conn.execute("DELETE FROM task_submissions WHERE task_id = ?", (task_id,))
            await conn.execute("DELETE FROM task_assignments WHERE id = ?", (task_id,))
            await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (dosen_id, student_id))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_3_escaped_html_in_cmd_cek_user():
    """Verifikasi: cmd_cek_user melakukan html.escape pada nama pengguna,
    sehingga entitas seperti '<', '>', dan '&' tidak merusak parser Telegram."""
    db = Database()
    conn = await db.connect()
    
    uid = 88003
    admin_id = 88004
    
    bad_name = "Budi <Hacker> & Co"
    await db.upsert_user_from_telegram(conn, telegram_id=uid, username="budi_hacker", first_name="Budi", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_profile_partial(conn, uid, {"full_name": bad_name})
    
    await db.upsert_user_from_telegram(conn, telegram_id=admin_id, username="admin_cek", first_name="Admin", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, admin_id, "admin")
    
    update = make_mock_update(user_id=admin_id, text=f"/cek_user {uid}")
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    ctx.args = [str(uid)]
    
    await commands.cmd_cek_user(update, ctx)
    
    reply_call = update.message.reply_text.call_args
    assert reply_call is not None, "reply_text was not called"
    reply_text = reply_call[0][0]
    
    try:
        # VERIFIKASI: bad_name di-escape, tidak ada tag mentah <Hacker>
        assert "<Hacker>" not in reply_text
        assert "&lt;Hacker&gt;" in reply_text
        assert "&amp;" in reply_text
    finally:
        try:
            await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (uid, admin_id))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_4_attendance_active_session_guard():
    """Verifikasi: cb_open_presensi menolak pembukaan sesi baru jika sesi aktif sudah berjalan untuk kelas yang sama."""
    db = Database()
    conn = await db.connect()
    
    admin_id = 88005
    await db.upsert_user_from_telegram(conn, telegram_id=admin_id, username="admin_presensi", first_name="Admin", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, admin_id, "owner")
    
    # Sesi aktif berjalan
    sid1 = await db.open_attendance_session(conn, class_id="kelas_duplikat", title="Sesi 1", opened_by=admin_id, chat_id=-100)
    
    # Panggil cb_open_presensi untuk kelas yang sama via callback "o:kelas_duplikat"
    update = make_mock_update(user_id=admin_id)
    q = MagicMock(spec=CallbackQuery)
    q.data = "o:kelas_duplikat"
    q.from_user = update.effective_user
    q.message = MagicMock(spec=Message)
    q.message.chat_id = -100
    q.message.message_id = 1001
    q.message.edit_text = AsyncMock()
    q.answer = AsyncMock()
    update.callback_query = q
    
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    
    await attendance.cb_open_presensi(update, ctx)
    
    # Cek sesi 1 tidak tertutup
    sess1_after = await db.get_attendance_session(conn, sid1)
    
    try:
        # VERIFIKASI: Sesi 1 tetap aktif (closed_at is None) dan edit_message_text memperingatkan sesi sudah aktif
        assert sess1_after["closed_at"] is None
        edit_call = q.edit_message_text.call_args[0][0]
        assert "sudah dibuka sebelumnya" in edit_call
    finally:
        try:
            await db.close_attendance_session(conn, sid1)
            await conn.execute("DELETE FROM attendance_sessions WHERE class_id = 'kelas_duplikat'")
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (admin_id,))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_5_contract_sequence_atomic():
    """Verifikasi: db.get_next_contract_seq mengembalikan sequence number yang meningkat secara atomic."""
    db = Database()
    conn = await db.connect()
    
    seq1 = await db.get_next_contract_seq(conn)
    seq2 = await db.get_next_contract_seq(conn)
    
    # VERIFIKASI: seq2 harus tepat seq1 + 1 (tidak duplikat)
    assert seq2 == seq1 + 1, f"Expected atomic increment, got seq1={seq1}, seq2={seq2}"


@pytest.mark.asyncio
async def test_qa_fix_6_self_approval_blocked():
    """Verifikasi: Staf internal/SDM tidak dapat menyetujui perubahan profil miliknya sendiri."""
    db = Database()
    conn = await db.connect()
    
    sdm_user_id = 88008
    await db.upsert_user_from_telegram(conn, telegram_id=sdm_user_id, username="sdm_user", first_name="SDM", last_name="Staff", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.set_role(conn, sdm_user_id, "internal")
    await db.set_profile_partial(conn, sdm_user_id, {"position_detail": ["d_umum_sdm"]})
    
    # SDM mengajukan perubahan profil
    req_id = await db.add_profile_request(conn, sdm_user_id, {"full_name": "SDM Naik Pangkat"})
    
    # SDM mencoba klik tombol approve a:<req_id>:1
    update = make_mock_update(user_id=sdm_user_id)
    q = MagicMock(spec=CallbackQuery)
    q.data = f"a:{req_id}:1"
    q.from_user = update.effective_user
    q.message = MagicMock(spec=Message)
    q.message.chat_id = sdm_user_id
    q.message.message_id = 1002
    q.message.text = "Pengajuan"
    q.message.edit_text = AsyncMock()
    q.answer = AsyncMock()
    update.callback_query = q
    
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    
    await commands.on_callback(update, ctx)
    
    # Cek status request di database
    req = await db.get_profile_request(conn, req_id)
    
    try:
        # VERIFIKASI: Self-approval ditolak dengan alert dan status tetap pending
        assert req["status"] == "pending", f"Expected pending status, got {req['status']}"
        q.answer.assert_called_with("❌ Anda tidak dapat memproses pengajuan profil Anda sendiri.", show_alert=True)
    finally:
        try:
            await conn.execute("DELETE FROM profile_change_requests WHERE id = ?", (req_id,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (sdm_user_id,))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_7_menfess_state_loss_protection():
    """Verifikasi: execute_menfess dengan state kosong tidak memotong saldo Agra pengguna dan tidak crash."""
    db = Database()
    conn = await db.connect()
    
    sender_id = 88009
    await db.upsert_user_from_telegram(conn, telegram_id=sender_id, username="sender_lost", first_name="Sender", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.add_agra(conn, target_id=sender_id, actor_id=sender_id, amount=10, description="Modal", chat_id=None, message_id=None)
    
    update = make_mock_update(user_id=sender_id)
    ctx = MagicMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    ctx.user_data = {} # State kosong (misal setelah restart)
    ctx.bot.send_message = AsyncMock()
    
    update.callback_query = MagicMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.edit_text = AsyncMock()
    
    # Jalankan execute_menfess
    res = await menfess.execute_menfess(update, ctx)
    bal = await db.agra_total(conn, sender_id)
    
    try:
        # VERIFIKASI: Saldo utuh 10 Agra dan pesan error dikirimkan
        assert bal == 10, f"Expected 10 Agra intact, got {bal}"
        update.callback_query.message.edit_text.assert_called_with("❌ Sesi menfess telah kedaluwarsa atau data tidak ditemukan. Silakan mulai ulang dengan perintah /menfess.")
    finally:
        try:
            await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id = ?", (sender_id,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (sender_id,))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qa_fix_8_spec_commands_registered():
    """Verifikasi: Perintah /laporan, /leaderboard, dan /pay terdaftar pada dispatcher."""
    from bot.handlers.register import register_all
    app = MagicMock()
    handlers_registered = []
    
    def fake_add_handler(h, group=None):
        handlers_registered.append(h)
    app.add_handler = fake_add_handler
    app.bot_data = {}
    
    db = Database()
    register_all(app, db)
    
    from telegram.ext import CommandHandler
    cmd_names = set()
    for h in handlers_registered:
        if isinstance(h, CommandHandler):
            for cmd in h.commands:
                cmd_names.add(cmd)
                
    assert "laporan" in cmd_names, "/laporan must be registered"
    assert "leaderboard" in cmd_names, "/leaderboard must be registered"
    assert "pay" in cmd_names, "/pay must be registered"


@pytest.mark.asyncio
async def test_qa_bug_8_transfer_negative_and_self():
    """Verifikasi proteksi transfer agra:
    1. Transfer angka negatif / nol harus ditolak.
    2. Transfer ke diri sendiri harus ditolak."""
    db = Database()
    conn = await db.connect()
    
    actor_id = 88010
    target_id = 88011
    
    await db.upsert_user_from_telegram(conn, telegram_id=actor_id, username="actor_tf", first_name="Actor", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.upsert_user_from_telegram(conn, telegram_id=target_id, username="target_tf", first_name="Target", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
    await db.add_agra(conn, target_id=actor_id, actor_id=actor_id, amount=100, description="Modal", chat_id=None, message_id=None)
    
    # 1. Test negative amount
    update_neg = make_mock_update(user_id=actor_id, text="/transfer -10 | bayar")
    update_neg.message.reply_to_message = MagicMock()
    update_neg.message.reply_to_message.from_user = MagicMock()
    update_neg.message.reply_to_message.from_user.id = target_id
    update_neg.message.reply_to_message.from_user.is_bot = False
    update_neg.message.entities = []
    
    ctx_neg = MagicMock()
    ctx_neg.application = MagicMock()
    ctx_neg.application.bot_data = {"db": db, "conn": conn}
    ctx_neg.args = ["-10", "|", "bayar"]
    await commands.cmd_transfer(update_neg, ctx_neg)
    
    reply_neg = update_neg.message.reply_text.call_args[0][0]
    assert "Nominal transfer harus lebih besar dari 0" in reply_neg
    
    # 2. Test self transfer
    update_self = make_mock_update(user_id=actor_id, text="/transfer 10 | bayar diri")
    update_self.message.reply_to_message = MagicMock()
    update_self.message.reply_to_message.from_user = MagicMock()
    update_self.message.reply_to_message.from_user.id = actor_id # Self!
    update_self.message.reply_to_message.from_user.is_bot = False
    update_self.message.entities = []
    
    ctx_self = MagicMock()
    ctx_self.application = MagicMock()
    ctx_self.application.bot_data = {"db": db, "conn": conn}
    ctx_self.args = ["10", "|", "bayar diri"]
    await commands.cmd_transfer(update_self, ctx_self)
    
    reply_self = update_self.message.reply_text.call_args[0][0]
    assert "Tidak bisa transfer ke diri sendiri" in reply_self
    
    # Cleanup
    try:
        await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id IN (?, ?)", (actor_id, target_id))
        await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (actor_id, target_id))
        await conn.commit()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_cmd_help_all_roles(mock_app):
    """Verifikasi bahwa help_for_role dan cmd_help tidak melempar NameError pada semua role."""
    from bot.database import (
        ROLE_STUDENT, ROLE_ADMIN, ROLE_OWNER, ROLE_INTERNAL,
        ROLE_BEM, ROLE_MABA, ROLE_CHARYARTHI, ROLE_PURVA, ROLE_PUBLIC
    )
    all_roles = [
        ROLE_STUDENT, ROLE_ADMIN, ROLE_OWNER, ROLE_INTERNAL,
        ROLE_BEM, ROLE_MABA, ROLE_CHARYARTHI, ROLE_PURVA, ROLE_PUBLIC
    ]

    for role in all_roles:
        text = commands.help_for_role(role, {})
        assert "Perintah umum" in text
        assert "/profile" in text

    db = Database()
    conn = await db.connect()
    try:
        test_uid = 9988776655
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=test_uid,
            username="tester_help",
            first_name="Help",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={}
        )
        await db.set_role(conn, test_uid, ROLE_STUDENT)

        update = make_mock_update(user_id=test_uid, text="/help")
        ctx = MagicMock()
        ctx.application = mock_app
        ctx.application.bot_data = {"db": db, "conn": conn}

        await commands.cmd_help(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "Perintah umum" in reply
        assert "Shishya" in reply
    finally:
        await conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_uid,))
        await conn.commit()

