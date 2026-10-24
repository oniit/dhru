import asyncio
import os
import pytest
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
    ROLES_ORDER,
)
from bot.handlers.common import role_display, display_keys_for_role, profile_from_row, render_charyarthi_quiz_view
from bot.settings import (
    get_charyarthi_divisions,
    get_division_label,
    resolve_division_id,
    CHARYARTHI_OPREC_OPEN,
    CHARYARTHI_GFORM_LINK,
)


@pytest.mark.asyncio
async def test_charyarthi_hierarchy_and_display():
    # 1. Test Role Constants & Hierarchy Order
    assert ROLE_CHARYARTHI == "charyarthi"
    assert ROLES_ORDER == (
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
    assert ROLES_ORDER.index(ROLE_MABA) < ROLES_ORDER.index(ROLE_CHARYARTHI) < ROLES_ORDER.index(ROLE_PUBLIC)

    # 2. Test Role Display Name
    assert role_display(ROLE_CHARYARTHI) == "Chāryārthī"

    # 3. Test Divisions & Labels
    divs = get_charyarthi_divisions()
    assert len(divs) > 0
    # Dosen, editor, dekan, and Biro Eksternal should be in divisions
    div_ids = [d[0] for d in divs]
    assert "d_dosen" in div_ids
    assert "d_editor" in div_ids
    assert "d_dekan" in div_ids
    assert "d_guru_besar" in div_ids
    assert "d_pembina" in div_ids
    assert "d_mpps" in div_ids
    assert "d_pfp" in div_ids
    assert "d_pr" in div_ids
    # Nayaka (Rektor) should be excluded
    assert "d_rektor" not in div_ids

    assert get_division_label("d_editor") == "Editorial & Konten"


@pytest.mark.asyncio
async def test_charyarthi_db_lifecycle():
    db = Database()
    conn = await db.connect()
    test_uid = 9988776655

    try:
        # Create user
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=test_uid,
            username="candidate_charya",
            first_name="Candidate",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        row = await db.get_user(conn, test_uid)
        assert row["role"] == ROLE_PUBLIC

        # Candidate applies: sets profile with full_name, target_division_1, target_division_2
        await db.set_profile_partial(conn, test_uid, {
            "full_name": "Calon Staf Dhruva",
            "target_division_1": "d_editor",
            "target_division_2": "d_eksternal",
        })
        await db.set_role(conn, test_uid, ROLE_CHARYARTHI)

        row = await db.get_user(conn, test_uid)
        assert row["role"] == ROLE_CHARYARTHI
        prof = profile_from_row(row)
        assert prof["full_name"] == "Calon Staf Dhruva"
        assert prof["target_division_1"] == "d_editor"
        assert prof["target_division_2"] == "d_eksternal"

        # Check display keys include division choices for Charyarthi
        keys = display_keys_for_role(ROLE_CHARYARTHI, prof)
        assert "target_division_1" in keys
        assert "target_division_2" in keys

        # Acceptance: Promote to INTERNAL and set accepted division
        accepted_div = prof["target_division_1"]
        await db.set_profile_partial(conn, test_uid, {
            "position_detail": [accepted_div],
            "application_status": "ACCEPTED",
            "accepted_division": accepted_div,
        })
        await db.set_role(conn, test_uid, ROLE_INTERNAL)

        row_acc = await db.get_user(conn, test_uid)
        assert row_acc["role"] == ROLE_INTERNAL
        prof_acc = profile_from_row(row_acc)
        assert "d_editor" in prof_acc["position_detail"]

        # Rejection test: Rollback to PUBLIC
        await db.set_role(conn, test_uid, ROLE_PUBLIC)
        await db.set_profile_partial(conn, test_uid, {
            "application_status": "REJECTED",
        })
        row_rej = await db.get_user(conn, test_uid)
        assert row_rej["role"] == ROLE_PUBLIC
        prof_rej = profile_from_row(row_rej)
        assert prof_rej["application_status"] == "REJECTED"

    finally:
        # Cleanup test user from DB
        await conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_uid,))
        await conn.commit()


@pytest.mark.asyncio
async def test_charyarthi_dynamic_settings():
    db = Database()
    conn = await db.connect()
    from bot.handlers.common import is_charyarthi_oprec_open, get_active_charyarthi_divisions

    # Test toggle master switch
    await db.set_setting(conn, "charyarthi_oprec_open", "0")
    await conn.commit()
    assert await is_charyarthi_oprec_open(db, conn) is False

    await db.set_setting(conn, "charyarthi_oprec_open", "1")
    await conn.commit()
    assert await is_charyarthi_oprec_open(db, conn) is True

    # Test toggle division switch
    await db.set_setting(conn, "charyarthi_div_d_editor", "1")
    await conn.commit()
    active_before = await get_active_charyarthi_divisions(db, conn)
    active_ids_before = [d[0] for d in active_before]
    assert "d_editor" in active_ids_before

    # Disable d_editor
    await db.set_setting(conn, "charyarthi_div_d_editor", "0")
    await conn.commit()
    active_after = await get_active_charyarthi_divisions(db, conn)
    active_ids_after = [d[0] for d in active_after]
    assert "d_editor" not in active_ids_after

    # Re-enable d_editor
    await db.set_setting(conn, "charyarthi_div_d_editor", "1")
    await conn.commit()
    active_restored = await get_active_charyarthi_divisions(db, conn)
    active_ids_restored = [d[0] for d in active_restored]
    assert "d_editor" in active_ids_restored


@pytest.mark.asyncio
async def test_both_registrations_forwarding_to_pendaftar_channel():
    from unittest.mock import AsyncMock, MagicMock
    from telegram import Update, Message, User, Chat, CallbackQuery
    from bot.handlers import commands
    from bot.settings import PENDAFTAR_CH_ID

    db = Database()
    conn = await db.connect()

    uid_maba = 7711223344
    uid_charya = 7711223355

    try:
        # 1. Setup user MABA
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=uid_maba,
            username="calon_maba",
            first_name="Maba",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.set_profile_partial(conn, uid_maba, {
            "full_name": "Calon Maba Satu",
            "join_reason": "Ingin belajar",
        })
        # Tambah promo valid
        await conn.execute(
            "INSERT INTO promo_verifications (user_id, promo_type, link, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid_maba, "lpm", "https://t.me/c/123/45", "VALID", 1000)
        )
        await conn.commit()

        # Mock callback query untuk maba:claim_ospek
        update_maba = MagicMock(spec=Update)
        user_maba = MagicMock(spec=User)
        user_maba.id = uid_maba
        user_maba.username = "calon_maba"
        user_maba.first_name = "Maba"
        update_maba.effective_user = user_maba

        q_maba = MagicMock(spec=CallbackQuery)
        q_maba.data = "maba:claim_ospek"
        q_maba.from_user = user_maba
        q_maba.answer = AsyncMock()
        q_maba.edit_message_text = AsyncMock()
        update_maba.callback_query = q_maba

        ctx_maba = MagicMock()
        ctx_maba.bot = MagicMock()
        ctx_maba.bot.send_message = AsyncMock()
        ctx_maba.application = MagicMock()
        ctx_maba.application.bot_data = {"db": db, "conn": conn}

        # Jalankan callback maba
        await commands.on_callback(update_maba, ctx_maba)

        # Verifikasi maba
        row_m = await db.get_user(conn, uid_maba)
        assert row_m["role"] == ROLE_MABA
        q_maba.edit_message_text.assert_called_once()
        if PENDAFTAR_CH_ID:
            ctx_maba.bot.send_message.assert_called_once()
            call_kwargs = ctx_maba.bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == PENDAFTAR_CH_ID
            assert "Calon Maba Satu" in call_kwargs["text"]
            assert "Ingin belajar" in call_kwargs["text"]

        # 2. Setup user Charyarthi
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=uid_charya,
            username="calon_charya",
            first_name="Charya",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.set_profile_partial(conn, uid_charya, {
            "full_name": "Calon Charya Satu",
            "charyarthi_reason": "Ingin mengabdi",
            "target_division_1": "d_editor",
            "target_division_2": "d_eksternal",
        })
        # Tambah promo valid
        await conn.execute(
            "INSERT INTO promo_verifications (user_id, promo_type, link, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid_charya, "story", "https://t.me/c/123/46", "VALID", 1000)
        )
        await conn.commit()

        # Tambah soal dan jawaban tes divisi untuk uid_charya
        await db.clear_charyarthi_questions(conn, "d_editor")
        qid_test = await db.add_charyarthi_question(conn, "d_editor", "Apa portofolio Anda?")
        await db.save_charyarthi_answer(conn, uid_charya, "d_editor", qid_test, "Portofolio penulisan saya.")

        # Mock callback query untuk charyarthi:submit
        update_charya = MagicMock(spec=Update)
        user_charya = MagicMock(spec=User)
        user_charya.id = uid_charya
        user_charya.username = "calon_charya"
        user_charya.first_name = "Charya"
        update_charya.effective_user = user_charya

        q_charya = MagicMock(spec=CallbackQuery)
        q_charya.data = "charyarthi:submit"
        q_charya.from_user = user_charya
        q_charya.answer = AsyncMock()
        q_charya.edit_message_text = AsyncMock()
        update_charya.callback_query = q_charya

        ctx_charya = MagicMock()
        ctx_charya.bot = MagicMock()
        ctx_charya.bot.send_message = AsyncMock()
        ctx_charya.application = MagicMock()
        ctx_charya.application.bot_data = {"db": db, "conn": conn}

        # Jalankan callback charyarthi
        await commands.on_callback(update_charya, ctx_charya)

        # Verifikasi charyarthi
        row_c = await db.get_user(conn, uid_charya)
        assert row_c["role"] == ROLE_CHARYARTHI
        prof_c = profile_from_row(row_c)
        assert prof_c["application_status"] == "PENDING"
        q_charya.edit_message_text.assert_called_once()
        if PENDAFTAR_CH_ID:
            sent_chats = [c.kwargs["chat_id"] for c in ctx_charya.bot.send_message.call_args_list]
            assert PENDAFTAR_CH_ID in sent_chats
            pendaftar_call = next(c for c in ctx_charya.bot.send_message.call_args_list if c.kwargs["chat_id"] == PENDAFTAR_CH_ID)
            call_kwargs_c = pendaftar_call.kwargs
            assert "PENDAFTARAN CHARYA (CALON STAF)" in call_kwargs_c["text"]
            assert "Calon Charya Satu" in call_kwargs_c["text"]
            assert "Ingin mengabdi" in call_kwargs_c["text"]
            assert call_kwargs_c["reply_markup"] is not None
        from bot.settings import SDM_CH_ID, SDM_GID
        sdm_target = SDM_CH_ID or SDM_GID
        if sdm_target:
            sdm_calls = [c for c in ctx_charya.bot.send_message.call_args_list if c.kwargs["chat_id"] == sdm_target]
            assert len(sdm_calls) >= 1
            assert "JAWABAN TES DIVISI (TIM SDM)" in sdm_calls[0].kwargs["text"]
            # SDM receives answer sheet only, without applicant decision buttons
            for c in sdm_calls:
                assert c.kwargs.get("reply_markup") is None

    finally:
        try:
            await db.clear_charyarthi_questions(conn, "d_editor")
            await db.clear_charyarthi_user_answers(conn, uid_charya)
            await conn.execute("DELETE FROM promo_verifications WHERE user_id IN (?, ?)", (uid_maba, uid_charya))
            await conn.execute("DELETE FROM users WHERE telegram_id IN (?, ?)", (uid_maba, uid_charya))
            await conn.commit()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_charyarthi_acc_and_rej_callback():
    from unittest.mock import AsyncMock, MagicMock
    from telegram import Update, User, CallbackQuery
    from bot.handlers import commands
    from bot.settings import OWNER_ID

    db = Database()
    conn = await db.connect()
    uid_candidate = 8822334455

    try:
        # Create candidate user
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=uid_candidate,
            username="candidate_acc",
            first_name="Candidate",
            last_name="Acc",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.set_profile_partial(conn, uid_candidate, {
            "full_name": "Calon Lulus",
            "target_division_1": "d_editor",
            "target_division_2": "d_eksternal",
            "application_status": "PENDING"
        })
        await db.set_role(conn, uid_candidate, ROLE_CHARYARTHI)

        # Mock Admin Callback Query for ACC
        admin_user = MagicMock(spec=User)
        admin_user.id = OWNER_ID
        admin_user.username = "owner"
        admin_user.first_name = "Owner"

        q_acc = MagicMock(spec=CallbackQuery)
        q_acc.data = f"charyarthi:acc:{uid_candidate}:1"
        q_acc.from_user = admin_user
        q_acc.message = MagicMock()
        q_acc.message.text = "Pendaftaran Chāryārthī"
        q_acc.message.text_html = "<b>Pendaftaran Chāryārthī</b>"
        q_acc.answer = AsyncMock()
        q_acc.edit_message_text = AsyncMock()
        q_acc.edit_message_reply_markup = AsyncMock()

        update_acc = MagicMock(spec=Update)
        update_acc.callback_query = q_acc

        ctx_acc = MagicMock()
        ctx_acc.bot = MagicMock()
        ctx_acc.bot.send_message = AsyncMock()
        ctx_acc.application = MagicMock()
        ctx_acc.application.bot_data = {"db": db, "conn": conn}

        # Run on_callback for ACC
        await commands.on_callback(update_acc, ctx_acc)

        # Check DB state
        row_after_acc = await db.get_user(conn, uid_candidate)
        assert row_after_acc["role"] == ROLE_INTERNAL
        prof_after_acc = profile_from_row(row_after_acc)
        assert prof_after_acc["application_status"] == "ACCEPTED"
        assert "d_editor" in prof_after_acc["position_detail"]

        # Verify duplicate decision is blocked
        await commands.on_callback(update_acc, ctx_acc)
        q_acc.answer.assert_called_with("⚠️ Lamaran ini sudah pernah diputuskan sebelumnya (ACCEPTED).", show_alert=True)

        # Reset candidate to PENDING to test REJ callback
        await db.set_role(conn, uid_candidate, ROLE_CHARYARTHI)
        await db.set_profile_partial(conn, uid_candidate, {"application_status": "PENDING"})

        # Now test REJ callback
        q_rej = MagicMock(spec=CallbackQuery)
        q_rej.data = f"charyarthi:rej:{uid_candidate}"
        q_rej.from_user = admin_user
        q_rej.message = MagicMock()
        q_rej.message.text = "Pendaftaran Chāryārthī"
        q_rej.message.text_html = "<b>Pendaftaran Chāryārthī</b>"
        q_rej.answer = AsyncMock()
        q_rej.edit_message_text = AsyncMock()
        q_rej.edit_message_reply_markup = AsyncMock()

        update_rej = MagicMock(spec=Update)
        update_rej.callback_query = q_rej

        await commands.on_callback(update_rej, ctx_acc)

        row_after_rej = await db.get_user(conn, uid_candidate)
        assert row_after_rej["role"] == ROLE_PUBLIC
        prof_after_rej = profile_from_row(row_after_rej)
        assert prof_after_rej["application_status"] == "REJECTED"

    finally:
        try:
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid_candidate,))
            await conn.commit()
            await conn.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_charyarthi_division_questions_and_answers():
    # 1. Test resolve_division_id
    assert resolve_division_id("editor") == "d_editor"
    assert resolve_division_id("d_editor") == "d_editor"
    assert resolve_division_id("editorial") == "d_editor"
    assert resolve_division_id("sdm") == "d_hrd"
    assert resolve_division_id("non_existent_random") is None

    db = Database()
    conn = await db.connect()
    div_test = "d_editor"
    test_uid = 9988771122

    try:
        # Clear any preexisting questions for test division
        await db.clear_charyarthi_questions(conn, div_test)

        # 2. Test bulk questions setup
        sample_questions = [
            "Ceritakan portofolio dan tulisan Anda.",
            "Apa tools editing yang Anda kuasai?",
            "Bagaimana cara Anda membagi waktu kuliah dan staf?"
        ]
        await db.set_charyarthi_questions_bulk(conn, div_test, sample_questions)

        qs = await db.get_charyarthi_questions(conn, div_test)
        assert len(qs) == 3
        assert [q["question_order"] for q in qs] == [1, 2, 3]
        assert qs[0]["question_text"] == sample_questions[0]

        # 3. Test add question
        new_qid = await db.add_charyarthi_question(conn, div_test, "Apa ide konten inovatif Anda?")
        assert new_qid is not None
        qs_after_add = await db.get_charyarthi_questions(conn, div_test)
        assert len(qs_after_add) == 4
        assert qs_after_add[3]["question_order"] == 4

        # 4. Test delete question (delete question order 2)
        q2_id = qs_after_add[1]["id"]
        deleted = await db.delete_charyarthi_question(conn, q2_id)
        assert deleted is True

        qs_after_del = await db.get_charyarthi_questions(conn, div_test)
        assert len(qs_after_del) == 3
        # Should be renumbered to 1, 2, 3
        assert [q["question_order"] for q in qs_after_del] == [1, 2, 3]
        assert qs_after_del[1]["question_text"] == sample_questions[2]

        # 5. Test saving and retrieving candidate answers
        await db.clear_charyarthi_user_answers(conn, test_uid)
        ans_map = await db.get_charyarthi_answers(conn, test_uid, div_test)
        assert len(ans_map) == 0

        # Answer question 1
        q1_id = qs_after_del[0]["id"]
        await db.save_charyarthi_answer(conn, test_uid, div_test, q1_id, "Saya memiliki pengalaman menulis artikel...")
        ans_map1 = await db.get_charyarthi_answers(conn, test_uid, div_test)
        assert len(ans_map1) == 1
        assert ans_map1[q1_id] == "Saya memiliki pengalaman menulis artikel..."

        # 6. Test rendering quiz dashboard view (incomplete)
        text_inc, kb_inc = await render_charyarthi_quiz_view(test_uid, div_test, conn, db)
        assert "1/3 Soal Terisi" in text_inc
        # Check buttons: button "Belum Lengkap" should be present
        all_cb_data = [btn.callback_data for row in kb_inc.inline_keyboard for btn in row if btn.callback_data]
        assert "charyarthi:not_ready" in all_cb_data
        assert f"charyarthi:ready:{div_test}" not in all_cb_data

        # Answer the remaining questions
        q2_new_id = qs_after_del[1]["id"]
        q3_new_id = qs_after_del[2]["id"]
        await db.save_charyarthi_answer(conn, test_uid, div_test, q2_new_id, "Saya menggunakan manajemen kalender.")
        await db.save_charyarthi_answer(conn, test_uid, div_test, q3_new_id, "Ide konten reels informatif kampus.")

        # 7. Test rendering quiz dashboard view (complete)
        text_comp, kb_comp = await render_charyarthi_quiz_view(test_uid, div_test, conn, db)
        assert "3/3 Soal Terisi" in text_comp
        all_cb_data_comp = [btn.callback_data for row in kb_comp.inline_keyboard for btn in row if btn.callback_data]
        assert f"charyarthi:ready:{div_test}" in all_cb_data_comp
        assert "charyarthi:not_ready" not in all_cb_data_comp

    finally:
        try:
            await db.clear_charyarthi_questions(conn, div_test)
            await db.clear_charyarthi_user_answers(conn, test_uid)
            await conn.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_charyarthi_division_confirmation_and_lock():
    from unittest.mock import AsyncMock, MagicMock
    from telegram import Update, User, CallbackQuery
    from bot.handlers import commands

    db = Database()
    conn = await db.connect()
    test_uid = 9988112233
    div_test = "d_editor"

    try:
        # 1. Setup candidate user
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=test_uid,
            username="candidate_lock_test",
            first_name="Lock",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )

        # 2. Check quiz view directly: 'charyarthi:reselect' must NOT exist in quiz view
        _, kb_quiz = await render_charyarthi_quiz_view(test_uid, div_test, conn, db)
        quiz_cbs = [btn.callback_data for row in kb_quiz.inline_keyboard for btn in row if btn.callback_data]
        assert "charyarthi:reselect" not in quiz_cbs

        # 3. Test callback query: charyarthi:div1:d_editor triggers confirmation message
        cand_user = MagicMock(spec=User)
        cand_user.id = test_uid
        cand_user.username = "candidate_lock_test"
        cand_user.first_name = "Lock"

        q_div1 = MagicMock(spec=CallbackQuery)
        q_div1.data = f"charyarthi:div1:{div_test}"
        q_div1.from_user = cand_user
        q_div1.answer = AsyncMock()
        q_div1.edit_message_text = AsyncMock()

        update_div1 = MagicMock(spec=Update)
        update_div1.callback_query = q_div1

        ctx = MagicMock()
        ctx.bot = MagicMock()
        ctx.application = MagicMock()
        ctx.application.bot_data = {"db": db, "conn": conn}

        await commands.on_callback(update_div1, ctx)

        q_div1.edit_message_text.assert_called_once()
        call_args = q_div1.edit_message_text.call_args
        confirm_text = call_args.args[0]
        confirm_markup = call_args.kwargs.get("reply_markup")

        # Verify confirmation prompt text
        assert "@dhruvarsip" in confirm_text
        assert "tidak bisa mengganti divisi" in confirm_text

        # Verify buttons in confirmation prompt
        confirm_cbs = [btn.callback_data for row in confirm_markup.inline_keyboard for btn in row if btn.callback_data]
        assert f"charyarthi:confirm_div1:{div_test}" in confirm_cbs
        assert "charyarthi:reselect" in confirm_cbs

        # 4. Test confirming division choice: charyarthi:confirm_div1:d_editor
        q_confirm = MagicMock(spec=CallbackQuery)
        q_confirm.data = f"charyarthi:confirm_div1:{div_test}"
        q_confirm.from_user = cand_user
        q_confirm.answer = AsyncMock()
        q_confirm.edit_message_text = AsyncMock()

        update_confirm = MagicMock(spec=Update)
        update_confirm.callback_query = q_confirm

        await commands.on_callback(update_confirm, ctx)

        # Profile target_division_1 must be updated
        row = await db.get_user(conn, test_uid)
        prof = profile_from_row(row)
        assert prof.get("target_division_1") == div_test

    finally:
        try:
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_uid,))
            await conn.commit()
            await conn.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_charyarthi_long_answers_preview_and_forwarding():
    from unittest.mock import AsyncMock, MagicMock
    from telegram import Update, User, CallbackQuery
    from bot.handlers import commands
    from bot.handlers.common import render_charyarthi_quiz_preview_page
    from bot.settings import SDM_CH_ID, SDM_GID, PENDAFTAR_CH_ID

    db = Database()
    conn = await db.connect()
    uid = 9911882244
    div_id = "d_editor"

    try:
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=uid,
            username="long_ans_user",
            first_name="Long",
            last_name="Answer",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.clear_charyarthi_questions(conn, div_id)
        q1_id = await db.add_charyarthi_question(conn, div_id, "Pertanyaan esai pertama?")
        q2_id = await db.add_charyarthi_question(conn, div_id, "Pertanyaan esai kedua?")

        # Super long answers (> 3000 chars)
        long_ans1 = "A" * 3200
        long_ans2 = "B" * 2800
        await db.save_charyarthi_answer(conn, uid, div_id, q1_id, long_ans1)
        await db.save_charyarthi_answer(conn, uid, div_id, q2_id, long_ans2)

        # 1. Test render_charyarthi_quiz_preview_page
        text_p0, kb_p0 = await render_charyarthi_quiz_preview_page(uid, div_id, 0, conn, db)
        assert len(text_p0) <= 4096
        assert "Soal 1 dari 2" in text_p0
        assert "dipotong di tampilan pratinjau" in text_p0

        text_p1, kb_p1 = await render_charyarthi_quiz_preview_page(uid, div_id, 1, conn, db)
        assert len(text_p1) <= 4096
        assert "Soal 2 dari 2" in text_p1

        # 2. Test callback charyarthi:preview:{div_id} redirects to paginated preview
        u = MagicMock(spec=User)
        u.id = uid
        u.username = "long_ans_user"
        u.first_name = "Long"

        q_prev = MagicMock(spec=CallbackQuery)
        q_prev.data = f"charyarthi:preview:{div_id}"
        q_prev.from_user = u
        q_prev.answer = AsyncMock()
        q_prev.edit_message_text = AsyncMock()

        up_prev = MagicMock(spec=Update)
        up_prev.callback_query = q_prev

        ctx = MagicMock()
        ctx.bot = MagicMock()
        ctx.bot.send_message = AsyncMock()
        ctx.application = MagicMock()
        ctx.application.bot_data = {"db": db, "conn": conn}

        await commands.on_callback(up_prev, ctx)
        q_prev.edit_message_text.assert_called_once()
        sent_prev_text = q_prev.edit_message_text.call_args.args[0]
        assert len(sent_prev_text) <= 4096
        assert "Pertanyaan esai pertama?" in sent_prev_text

        # Test paginated preview callback prev_q:0
        q_prev_q = MagicMock(spec=CallbackQuery)
        q_prev_q.data = f"charyarthi:prev_q:{div_id}:0"
        q_prev_q.from_user = u
        q_prev_q.answer = AsyncMock()
        q_prev_q.edit_message_text = AsyncMock()
        up_prev_q = MagicMock(spec=Update)
        up_prev_q.callback_query = q_prev_q
        await commands.on_callback(up_prev_q, ctx)
        q_prev_q.edit_message_text.assert_called_once()
        sent_q_text = q_prev_q.edit_message_text.call_args.args[0]
        assert "Soal 1 dari 2" in sent_q_text

        # 3. Test submitting with long reason and long answers
        long_reason = "Alasan mendaftar yang sangat panjang dan detail " * 40  # > 1600 chars
        await db.set_profile_partial(conn, uid, {
            "full_name": "Long Answer Candidate",
            "charyarthi_reason": long_reason,
            "target_division_1": div_id,
        })
        await db.add_promo_verification(conn, uid, "https://t.me/grup_lpm/777", promo_type="lpm", status="VALID")

        q_sub = MagicMock(spec=CallbackQuery)
        q_sub.data = "charyarthi:submit"
        q_sub.from_user = u
        q_sub.answer = AsyncMock()
        q_sub.edit_message_text = AsyncMock()

        up_sub = MagicMock(spec=Update)
        up_sub.callback_query = q_sub

        sent_msg_mock = MagicMock()
        sent_msg_mock.message_id = 12345
        ctx.bot.send_message = AsyncMock(return_value=sent_msg_mock)

        await commands.on_callback(up_sub, ctx)

        # Verify messages sent to SDM target and PENDAFTAR_CH_ID never exceed 4096 chars
        sdm_target = SDM_CH_ID or SDM_GID
        for c in ctx.bot.send_message.call_args_list:
            text_arg = c.kwargs.get("text", "")
            assert len(text_arg) <= 4096

        if sdm_target:
            sdm_calls = [c for c in ctx.bot.send_message.call_args_list if c.kwargs.get("chat_id") == sdm_target]
            assert len(sdm_calls) >= 2  # Header + at least one chunk

        # 4. Test resetting user cleans charyarthi_answers
        answers_before = await db.get_charyarthi_answers(conn, uid, div_id)
        assert len(answers_before) == 2

        reset_res = await db.reset_user_all_data(conn, uid)
        assert reset_res.get("charyarthi_answers") == 2

        answers_after = await db.get_charyarthi_answers(conn, uid, div_id)
        assert len(answers_after) == 0

    finally:
        try:
            await db.clear_charyarthi_questions(conn, div_id)
            await db.clear_charyarthi_user_answers(conn, uid)
            await conn.execute("DELETE FROM promo_verifications WHERE user_id = ?", (uid,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
            await conn.commit()
            await conn.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_promo_keyword_not_leaked():
    from bot.handlers.promo import verify_lpm_link_embed
    from unittest.mock import patch, MagicMock, AsyncMock

    db = Database()
    conn = await db.connect()
    uid = 9911883355
    secret_keyword = "secret_lpm_token_xyz"
    link = "https://t.me/grup_test/100"

    try:
        mock_html = """
        <div class="tgme_widget_message_author accent_color">
            <a class="tgme_widget_message_author_name" href="https://t.me/tester">
                <span>Tester</span>
            </a>
        </div>
        <div class="tgme_widget_message_text js-message_text">Ini adalah pesan biasa tanpa token</div>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            is_valid, status, err_msg = await verify_lpm_link_embed(
                conn, db, user_id=uid, link=link, lpm_keyword=secret_keyword
            )
            assert is_valid is False
            assert status == "NO_KEYWORD"
            assert err_msg is not None
            # Must NOT leak secret_keyword
            assert secret_keyword not in err_msg
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_charyarthi_deep_qa_edge_cases():
    from unittest.mock import AsyncMock, MagicMock
    from telegram import Update, User, CallbackQuery, Message
    from bot.handlers import commands, messages
    from bot.handlers.commands import _render_admin_division_soal
    from bot.settings import SDM_CH_ID, SDM_GID, PENDAFTAR_CH_ID

    db = Database()
    conn = await db.connect()
    uid_test = 9922334411
    div_test = "d_pr"  # Biro Humas

    try:
        # 1. Setup user with previous REJECTED status
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=uid_test,
            username="qa_charya",
            first_name="QA",
            last_name="Tester",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.set_profile_partial(conn, uid_test, {
            "full_name": "QA Applicant",
            "application_status": "REJECTED"
        })
        await db.set_setting(conn, "charyarthi_oprec_open", "1")
        await db.set_setting(conn, f"charyarthi_div_{div_test}", "1")
        await conn.commit()

        # 2. Test /charyarthi command cleans REJECTED status and sets step
        u_mock = MagicMock(spec=User)
        u_mock.id = uid_test
        u_mock.username = "qa_charya"
        u_mock.first_name = "QA"

        msg_mock = MagicMock(spec=Message)
        msg_mock.text = "/charyarthi"
        msg_mock.reply_text = AsyncMock()

        up_cmd = MagicMock(spec=Update)
        up_cmd.effective_user = u_mock
        up_cmd.message = msg_mock

        ctx_mock = MagicMock()
        ctx_mock.bot = MagicMock()
        ctx_mock.bot.send_message = AsyncMock()
        ctx_mock.application = MagicMock()
        ctx_mock.application.bot_data = {"db": db, "conn": conn}

        await commands.cmd_charyarthi(up_cmd, ctx_mock)
        msg_mock.reply_text.assert_called_once()

        u_row = await db.get_user(conn, uid_test)
        assert u_row["onboarding_step"] == "CHARYARTHI_REASON"
        prof = profile_from_row(u_row)
        assert prof.get("application_status") is None  # Cleaned!

        # 3. Test empty input rejection in messages.py
        empty_msg = MagicMock(spec=Message)
        empty_msg.text = "   "
        empty_msg.caption = None
        empty_msg.photo = []
        empty_msg.reply_text = AsyncMock()

        up_empty = MagicMock(spec=Update)
        up_empty.effective_user = u_mock
        up_empty.effective_chat = MagicMock()
        up_empty.effective_chat.type = "private"
        up_empty.message = empty_msg

        await messages.on_private_message(up_empty, ctx_mock)
        empty_msg.reply_text.assert_called_once()
        assert "Alasan tidak boleh kosong" in empty_msg.reply_text.call_args.args[0]
        # Step remains CHARYARTHI_REASON
        u_row2 = await db.get_user(conn, uid_test)
        assert u_row2["onboarding_step"] == "CHARYARTHI_REASON"

        # 4. Fill valid reason
        valid_reason_msg = MagicMock(spec=Message)
        valid_reason_msg.text = "Alasan mendaftar yang jelas dan bermutu."
        valid_reason_msg.caption = None
        valid_reason_msg.photo = []
        valid_reason_msg.reply_text = AsyncMock()

        up_reason = MagicMock(spec=Update)
        up_reason.effective_user = u_mock
        up_reason.effective_chat = MagicMock()
        up_reason.effective_chat.type = "private"
        up_reason.message = valid_reason_msg

        await messages.on_private_message(up_reason, ctx_mock)
        valid_reason_msg.reply_text.assert_called_once()
        assert "Silakan pilih <b>Divisi</b>" in valid_reason_msg.reply_text.call_args.args[0]

        # 5. Confirm division choice
        q_conf = MagicMock(spec=CallbackQuery)
        q_conf.data = f"charyarthi:confirm_div1:{div_test}"
        q_conf.from_user = u_mock
        q_conf.answer = AsyncMock()
        q_conf.edit_message_text = AsyncMock()
        up_conf = MagicMock(spec=Update)
        up_conf.callback_query = q_conf
        await commands.on_callback(up_conf, ctx_mock)

        # 6. Add 1 question for div_test, check preview shows unescaped <i>(Belum diisi)</i>
        await db.clear_charyarthi_questions(conn, div_test)
        qid_p = await db.add_charyarthi_question(conn, div_test, "Bagaimana cara menyusun press release?")
        await db.clear_charyarthi_user_answers(conn, uid_test, div_test)

        q_prev = MagicMock(spec=CallbackQuery)
        q_prev.data = f"charyarthi:preview:{div_test}"
        q_prev.from_user = u_mock
        q_prev.answer = AsyncMock()
        q_prev.edit_message_text = AsyncMock()
        up_prev = MagicMock(spec=Update)
        up_prev.callback_query = q_prev

        await commands.on_callback(up_prev, ctx_mock)
        q_prev.edit_message_text.assert_called_once()
        prev_rendered = q_prev.edit_message_text.call_args.args[0]
        # Must contain unescaped <i>(Belum diisi)</i> and not &lt;i&gt;
        assert "<blockquote><i>(Belum diisi)</i></blockquote>" in prev_rendered
        assert "&lt;i&gt;" not in prev_rendered

        # 7. Test INPUT_SOAL_ADD step cleanup on menu navigation by authorized admin
        from bot.settings import OWNER_ID
        admin_mock = MagicMock(spec=User)
        admin_mock.id = OWNER_ID
        admin_mock.username = "owner"
        admin_mock.first_name = "Owner"

        await db.upsert_user_from_telegram(
            conn,
            telegram_id=OWNER_ID,
            username="owner",
            first_name="Owner",
            last_name="Dhruva",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )
        await db.set_onboarding_step(conn, OWNER_ID, f"INPUT_SOAL_ADD:{div_test}")
        q_nav = MagicMock(spec=CallbackQuery)
        q_nav.data = f"soal:adm_div:{div_test}"
        q_nav.from_user = admin_mock
        q_nav.answer = AsyncMock()
        q_nav.edit_message_text = AsyncMock()
        up_nav = MagicMock(spec=Update)
        up_nav.callback_query = q_nav

        await commands.on_callback(up_nav, ctx_mock)
        # Step must be cleared!
        admin_row_nav = await db.get_user(conn, OWNER_ID)
        assert admin_row_nav["onboarding_step"] is None

        # 8. Test _render_admin_division_soal with 25 long questions stays <= 4096 chars
        sample_bulk = [f"Pertanyaan panjang nomor {i} mengenai strategi divisi secara komprehensif..." * 3 for i in range(1, 26)]
        await db.set_charyarthi_questions_bulk(conn, div_test, sample_bulk)
        text_admin, kb_admin = await _render_admin_division_soal(div_test, conn, db)
        assert len(text_admin) <= 4096
        assert len(text_admin) <= 3800

        # 9. Test submitting candidate for division without essay questions notifies SDM
        div_empty_q = "d_dekan"
        await db.clear_charyarthi_questions(conn, div_empty_q)
        await db.set_profile_partial(conn, uid_test, {
            "target_division_1": div_empty_q,
            "target_division_2": None,
            "charyarthi_reason": "Saya ingin melamar ke dekanat.",
            "application_status": None,
        })
        await db.set_role(conn, uid_test, ROLE_PUBLIC)
        await db.add_promo_verification(conn, uid_test, "https://t.me/grup_lpm/999", promo_type="lpm", status="VALID")

        q_sub_no_q = MagicMock(spec=CallbackQuery)
        q_sub_no_q.data = "charyarthi:submit"
        q_sub_no_q.from_user = u_mock
        q_sub_no_q.answer = AsyncMock()
        q_sub_no_q.edit_message_text = AsyncMock()
        up_sub_no_q = MagicMock(spec=Update)
        up_sub_no_q.callback_query = q_sub_no_q

        ctx_mock.bot.send_message.reset_mock()
        ctx_mock.bot.send_message.return_value = MagicMock(message_id=98765)

        await commands.on_callback(up_sub_no_q, ctx_mock)

        sdm_target = SDM_CH_ID or SDM_GID
        if sdm_target:
            sdm_calls = [c for c in ctx_mock.bot.send_message.call_args_list if c.kwargs.get("chat_id") == sdm_target]
            assert len(sdm_calls) == 1
            assert "PENDAFTARAN CALON STAF (TIM SDM)" in sdm_calls[0].kwargs["text"]
            assert "tidak memerlukan tes esai tertulis tambahan" in sdm_calls[0].kwargs["text"]

    finally:
        try:
            await db.clear_charyarthi_questions(conn, div_test)
            await db.clear_charyarthi_user_answers(conn, uid_test)
            await conn.execute("DELETE FROM promo_verifications WHERE user_id = ?", (uid_test,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid_test,))
            await conn.commit()
            await conn.close()
        except Exception:
            pass





