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
        from bot.settings import SDM_GID
        if SDM_GID:
            sdm_calls = [c for c in ctx_charya.bot.send_message.call_args_list if c.kwargs["chat_id"] == SDM_GID]
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



