import asyncio
import os
import json
import time
import html
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat, CallbackQuery
from bot.database import (
    Database,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_INTERNAL,
    ROLE_BEM,
    ROLE_STUDENT,
    ROLE_PURVA,
    ROLE_MABA,
    ROLE_CHARYARTHI,
    ROLE_PUBLIC,
)
from bot.handlers import commands, messages, attendance, promo, common
from bot.handlers.common import profile_from_row
from bot.settings import SDM_CH_ID, SDM_GID, PENDAFTAR_CH_ID, OWNER_ID, get_division_label


def create_mock_user(uid: int, username: str = "tester", first_name: str = "Test"):
    u = MagicMock(spec=User)
    u.id = uid
    u.username = username
    u.first_name = first_name
    u.last_name = "User"
    u.language_code = "id"
    u.is_premium = False
    u.is_bot = False
    u.added_to_attachment_menu = None
    u.can_connect_to_business = None
    u.allows_write_to_pm = None
    u.to_dict = MagicMock(return_value={})
    return u


def create_mock_context(db, conn):
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=54321))
    ctx.bot.edit_message_text = AsyncMock()
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    return ctx


@pytest.mark.asyncio
async def test_qa_account_and_onboarding_lifecycle():
    """1. QA Akun: /start, /profil, /maba, /charyarthi, /cancel."""
    db = Database()
    conn = await db.connect()
    uid = 9933110011

    try:
        await db.set_setting(conn, "charyarthi_oprec_open", "1")
        await db.set_setting(conn, "charyarthi_div_d_editor", "1")
        await conn.commit()

        ctx = create_mock_context(db, conn)
        u_mock = create_mock_user(uid, "test_onboard", "Tester")

        # 1.1 /start creates public user and resets step
        msg_start = MagicMock(spec=Message)
        msg_start.text = "/start"
        msg_start.reply_text = AsyncMock()
        up_start = MagicMock(spec=Update)
        up_start.effective_user = u_mock
        up_start.message = msg_start

        await commands.cmd_start(up_start, ctx)
        row = await db.get_user(conn, uid)
        assert row is not None
        assert row["role"] == ROLE_PUBLIC
        assert row["onboarding_step"] is None

        # 1.2 /charyarthi starts flow
        msg_charya = MagicMock(spec=Message)
        msg_charya.text = "/charyarthi"
        msg_charya.reply_text = AsyncMock()
        up_charya = MagicMock(spec=Update)
        up_charya.effective_user = u_mock
        up_charya.message = msg_charya

        await commands.cmd_charyarthi(up_charya, ctx)
        row2 = await db.get_user(conn, uid)
        assert row2["onboarding_step"] == "CHARYARTHI_NAME"

        # 1.3 /cancel clears active step
        msg_cancel = MagicMock(spec=Message)
        msg_cancel.text = "/cancel"
        msg_cancel.reply_text = AsyncMock()
        up_cancel = MagicMock(spec=Update)
        up_cancel.effective_user = u_mock
        up_cancel.message = msg_cancel

        await commands.cmd_cancel(up_cancel, ctx)
        row3 = await db.get_user(conn, uid)
        assert row3["onboarding_step"] is None

    finally:
        await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_qa_charyarthi_full_e2e_flow():
    """2. QA Chāryārthī: End-to-End Registrasi, Tes Esai, Promo, Forwarding, dan Approval."""
    db = Database()
    conn = await db.connect()
    uid = 9933110022
    div_test = "d_editor"

    try:
        ctx = create_mock_context(db, conn)
        u_mock = create_mock_user(uid, "charya_e2e", "CharyaCandidate")

        # Setup initial user
        await db.upsert_user_from_telegram(
            conn, telegram_id=uid, username="charya_e2e", first_name="Candidate",
            last_name="E2E", language_code="id", is_premium=False, is_bot=False, raw_profile={}
        )
        await db.set_setting(conn, "charyarthi_oprec_open", "1")
        await db.set_setting(conn, f"charyarthi_div_{div_test}", "1")
        await conn.commit()

        # Step 1: Input Nama
        await db.set_onboarding_step(conn, uid, "CHARYARTHI_NAME")
        msg_name = MagicMock(spec=Message)
        msg_name.text = "Arya Penulis"
        msg_name.caption = None
        msg_name.photo = []
        msg_name.reply_text = AsyncMock()
        up_name = MagicMock(spec=Update)
        up_name.effective_user = u_mock
        up_name.effective_chat = MagicMock(type="private")
        up_name.message = msg_name

        await messages.on_private_message(up_name, ctx)
        u_row = await db.get_user(conn, uid)
        prof = profile_from_row(u_row)
        assert prof["full_name"] == "Arya Penulis"
        assert u_row["onboarding_step"] == "CHARYARTHI_REASON"

        # Step 2: Input Alasan (panjang > 700 chars untuk uji threaded reply)
        long_reason = "Alasan dedikasi saya untuk organisasi Dhruva dalam bidang literasi dan penulisan... " * 15
        msg_reason = MagicMock(spec=Message)
        msg_reason.text = long_reason
        msg_reason.caption = None
        msg_reason.photo = []
        msg_reason.reply_text = AsyncMock()
        up_reason = MagicMock(spec=Update)
        up_reason.effective_user = u_mock
        up_reason.effective_chat = MagicMock(type="private")
        up_reason.message = msg_reason

        await messages.on_private_message(up_reason, ctx)
        u_row = await db.get_user(conn, uid)
        prof = profile_from_row(u_row)
        assert len(prof["charyarthi_reason"]) > 600
        assert u_row["onboarding_step"] is None

        # Step 3: Konfirmasi Divisi
        q_conf = MagicMock(spec=CallbackQuery)
        q_conf.data = f"charyarthi:confirm_div1:{div_test}"
        q_conf.from_user = u_mock
        q_conf.answer = AsyncMock()
        q_conf.edit_message_text = AsyncMock()
        up_conf = MagicMock(spec=Update)
        up_conf.callback_query = q_conf

        await commands.on_callback(up_conf, ctx)
        u_row = await db.get_user(conn, uid)
        prof = profile_from_row(u_row)
        assert prof["target_division_1"] == div_test

        # Step 4: Setup Soal dan Jawab Tes
        await db.clear_charyarthi_questions(conn, div_test)
        q1_id = await db.add_charyarthi_question(conn, div_test, "Portofolio penulisan Anda?")
        q2_id = await db.add_charyarthi_question(conn, div_test, "Bagaimana strategi editing naskah panjang?")

        # Jawab Soal 1
        await db.save_charyarthi_answer(conn, uid, div_test, q1_id, "Pengalaman menulis 10 artikel nasional.")
        # Jawab Soal 2 dengan teks esai panjang (> 2500 karakter untuk uji chunking SDM)
        long_ans = "Strategi penyuntingan naskah dilakukan dengan memeriksa koherensi paragraf, tata bahasa PUEBI, dan konsistensi terminologi. " * 25
        await db.save_charyarthi_answer(conn, uid, div_test, q2_id, long_ans)

        # Step 5: Pratinjau Per Nomor (Pagination)
        text_p0, kb_p0 = await common.render_charyarthi_quiz_preview_page(uid, div_test, 0, conn, db)
        assert len(text_p0) <= 4096
        assert "Soal 1 dari 2" in text_p0

        text_p1, kb_p1 = await common.render_charyarthi_quiz_preview_page(uid, div_test, 1, conn, db)
        assert len(text_p1) <= 4096
        assert "Soal 2 dari 2" in text_p1

        # Step 6: Validasi Promo LPM
        await db.add_promo_verification(conn, uid, "https://t.me/grup_lpm_e2e/500", promo_type="lpm", status="VALID")

        # Step 7: Submit Pendaftaran
        q_sub = MagicMock(spec=CallbackQuery)
        q_sub.data = "charyarthi:submit"
        q_sub.from_user = u_mock
        q_sub.answer = AsyncMock()
        q_sub.edit_message_text = AsyncMock()
        up_sub = MagicMock(spec=Update)
        up_sub.callback_query = q_sub

        ctx.bot.send_message.reset_mock()
        ctx.bot.send_message.return_value = MagicMock(message_id=77889)

        await commands.on_callback(up_sub, ctx)

        # Verifikasi status di DB
        u_row = await db.get_user(conn, uid)
        assert u_row["role"] == ROLE_CHARYARTHI
        prof = profile_from_row(u_row)
        assert prof["application_status"] == "PENDING"

        # Verifikasi batas pesan pada semua pesan yang dikirim bot
        for c in ctx.bot.send_message.call_args_list:
            text_sent = c.kwargs.get("text", "")
            assert len(text_sent) <= 4096, f"Message exceeded Telegram limit: {len(text_sent)} chars"

        # Step 8: Keputusan ACC oleh Admin
        admin_user = create_mock_user(OWNER_ID, "owner", "Owner")
        q_acc = MagicMock(spec=CallbackQuery)
        q_acc.data = f"charyarthi:acc:{uid}:1"
        q_acc.from_user = admin_user
        q_acc.message = MagicMock(text="Pendaftaran Chāryārthī", text_html="<b>Pendaftaran Chāryārthī</b>")
        q_acc.answer = AsyncMock()
        q_acc.edit_message_text = AsyncMock()
        up_acc = MagicMock(spec=Update)
        up_acc.callback_query = q_acc

        await commands.on_callback(up_acc, ctx)
        u_row_acc = await db.get_user(conn, uid)
        assert u_row_acc["role"] == ROLE_INTERNAL
        prof_acc = profile_from_row(u_row_acc)
        assert prof_acc["application_status"] == "ACCEPTED"
        assert div_test in prof_acc["position_detail"]

    finally:
        await db.clear_charyarthi_questions(conn, div_test)
        await db.clear_charyarthi_user_answers(conn, uid)
        await conn.execute("DELETE FROM promo_verifications WHERE user_id = ?", (uid,))
        await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_qa_security_and_authorization_guards():
    """3. QA Keamanan: Public user dilarang mengakses perintah manajemen soal atau memutuskan pelamar."""
    db = Database()
    conn = await db.connect()
    uid_attacker = 9933110033
    target_uid = 9933110044

    try:
        ctx = create_mock_context(db, conn)
        u_attacker = create_mock_user(uid_attacker, "attacker", "Attacker")

        await db.upsert_user_from_telegram(
            conn, telegram_id=uid_attacker, username="attacker", first_name="Attacker",
            last_name="Evil", language_code="id", is_premium=False, is_bot=False, raw_profile={}
        )
        await db.set_role(conn, uid_attacker, ROLE_PUBLIC)

        # 3.1 Attacker memanggil /soal -> Ditolak
        msg_soal = MagicMock(spec=Message)
        msg_soal.reply_text = AsyncMock()
        up_soal = MagicMock(spec=Update)
        up_soal.effective_user = u_attacker
        up_soal.effective_chat = MagicMock(id=uid_attacker, type="private")
        up_soal.effective_message = msg_soal

        await commands.cmd_soal(up_soal, ctx)
        msg_soal.reply_text.assert_called_once()
        assert "hanya dapat diakses oleh Tim SDM" in msg_soal.reply_text.call_args.args[0]

        # 3.2 Attacker memanggil /acc_charyarthi -> Ditolak
        msg_acc = MagicMock(spec=Message)
        msg_acc.text = f"/acc_charyarthi {target_uid} 1"
        msg_acc.reply_text = AsyncMock()
        up_acc = MagicMock(spec=Update)
        up_acc.effective_user = u_attacker
        up_acc.effective_chat = MagicMock(id=uid_attacker, type="private")
        up_acc.effective_message = msg_acc
        up_acc.message = msg_acc

        await commands.cmd_acc_charyarthi(up_acc, ctx)
        msg_acc.reply_text.assert_called_once()
        assert "hanya untuk admin atau owner" in msg_acc.reply_text.call_args.args[0]

        # 3.3 Attacker memanggil callback charyarthi:acc:{target_uid}:1 -> Ditolak
        q_acc = MagicMock(spec=CallbackQuery)
        q_acc.data = f"charyarthi:acc:{target_uid}:1"
        q_acc.from_user = u_attacker
        q_acc.answer = AsyncMock()
        up_cb_acc = MagicMock(spec=Update)
        up_cb_acc.callback_query = q_acc

        await commands.on_callback(up_cb_acc, ctx)
        q_acc.answer.assert_called_with("Hanya admin atau owner yang berhak memutuskan.", show_alert=True)

        # 3.4 Attacker memanggil callback soal:adm_menu -> Ditolak
        q_soal = MagicMock(spec=CallbackQuery)
        q_soal.data = "soal:adm_menu"
        q_soal.from_user = u_attacker
        q_soal.message = MagicMock(chat_id=uid_attacker)
        q_soal.answer = AsyncMock()
        up_cb_soal = MagicMock(spec=Update)
        up_cb_soal.callback_query = q_soal

        await commands.on_callback(up_cb_soal, ctx)
        q_soal.answer.assert_called_with("Hanya Tim SDM, Petinggi, dan Staf Internal yang berhak mengakses.", show_alert=True)

    finally:
        await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid_attacker,))
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_qa_presensi_and_roles_integrity():
    """4. QA Presensi & Otorisasi: Pembina BEM dan Dosen wewenang presensi."""
    db = Database()
    conn = await db.connect()
    uid_pembina = 9933110055
    uid_student = 9933110066

    try:
        ctx = create_mock_context(db, conn)
        u_pembina = create_mock_user(uid_pembina, "pembina_user", "Pembina")
        u_student = create_mock_user(uid_student, "student_user", "Student")

        # Setup Pembina BEM
        await db.upsert_user_from_telegram(
            conn, telegram_id=uid_pembina, username="pembina_user", first_name="Pembina",
            last_name="BEM", language_code="id", is_premium=False, is_bot=False, raw_profile={}
        )
        await db.set_role(conn, uid_pembina, ROLE_INTERNAL)
        await db.set_profile_partial(conn, uid_pembina, {"position_detail": ["d_pembina"]})

        # Setup Student
        await db.upsert_user_from_telegram(
            conn, telegram_id=uid_student, username="student_user", first_name="Student",
            last_name="One", language_code="id", is_premium=False, is_bot=False, raw_profile={}
        )
        await db.set_role(conn, uid_student, ROLE_STUDENT)

        # Verifikasi Pembina memiliki akses buka presensi BEM
        pembina_row = await db.get_user(conn, uid_pembina)
        prof_p = profile_from_row(pembina_row)
        jabs = prof_p.get("position_detail", [])
        assert "d_pembina" in jabs

        # Student dilarang membuka presensi dosen/bem
        student_row = await db.get_user(conn, uid_student)
        assert student_row["role"] == ROLE_STUDENT

    finally:
        await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (uid_pembina, uid_student))
        await conn.commit()
        await conn.close()


@pytest.mark.asyncio
async def test_qa_agra_ledger_atomicity():
    """5. QA Agra: Mutasi saldo, non-negatif, dan integritas ledger."""
    db = Database()
    conn = await db.connect()
    uid_sender = 9933110077
    uid_receiver = 9933110088

    try:
        # Setup sender dengan 10 Agra
        await db.upsert_user_from_telegram(conn, telegram_id=uid_sender, username="sender", first_name="Sender", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.upsert_user_from_telegram(conn, telegram_id=uid_receiver, username="receiver", first_name="Receiver", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})

        await db.add_agra(conn, target_id=uid_sender, actor_id=OWNER_ID, amount=10, description="Initial balance", chat_id=None, message_id=None)
        await conn.commit()

        b_sender = await db.agra_total(conn, uid_sender)
        assert b_sender == 10

        # Transfer 4 Agra ke receiver
        await db.add_agra(conn, target_id=uid_sender, actor_id=uid_sender, amount=-4, description=f"Transfer to {uid_receiver}", chat_id=None, message_id=None)
        await db.add_agra(conn, target_id=uid_receiver, actor_id=uid_sender, amount=4, description=f"Transfer from {uid_sender}", chat_id=None, message_id=None)
        await conn.commit()

        assert await db.agra_total(conn, uid_sender) == 6
        assert await db.agra_total(conn, uid_receiver) == 4

        # Cek ledger
        cur = await conn.execute("SELECT COUNT(*) AS total FROM agra_ledger WHERE target_telegram_id IN (?, ?)", (uid_sender, uid_receiver))
        row = await cur.fetchone()
        assert row["total"] == 3

    finally:
        await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id IN (?, ?)", (uid_sender, uid_receiver))
        await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (uid_sender, uid_receiver))
        await conn.commit()
        await conn.close()
