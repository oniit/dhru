"""
Comprehensive QA & Regression Tests: Akun Kerja (/link_kerja) Integration for /pfp.
Tests:
- E2E flow: /link_kerja -> OTP -> /cek_akun_kerja -> /pfp (single & range) -> Agra & pfp_logs attribution
- /pfp daily & /pfp weekly aggregation under Main Account
- Group chat privacy (no Main Account ID leak in public groups)
- Cross-account duplicate kloter prevention & subset/partial-failure handling
- Cross-account concurrency lock (Main + Work account racing on /pfp)
- Security & privilege isolation (Work account never inherits Owner/Admin/PFP permissions)
- Linking integrity (no multi-main, no chains/cycles, missing user FK safety, OTP reuse protection)
- Unlink flow (/cek_akun_kerja, /unlink_kerja, callback buttons, IDOR protection)
- SQLite EXPLAIN QUERY PLAN verification (Turso read optimization / zero full table scans)
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.database import (
    Database,
    ROLE_ADMIN,
    ROLE_INTERNAL,
    ROLE_OWNER,
    ROLE_PUBLIC,
    ROLE_STUDENT,
    SCHEMA,
)
from bot.handlers import setup_handlers
import bot.handlers.pfp as pfp
import bot.handlers.promo as promo
from bot.timefmt import TZ, get_today_wib


def _make_sqlite_conn(enable_fk: bool = True):
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    if enable_fk:
        raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(SCHEMA)

    class _Cur:
        def __init__(self, cur):
            self._cur = cur
            self.lastrowid = cur.lastrowid
            self.rowcount = cur.rowcount

        async def fetchone(self):
            return self._cur.fetchone()

        async def fetchall(self):
            return self._cur.fetchall()

    class _Conn:
        async def execute(self, sql, params=()):
            cur = raw.execute(sql, params)
            return _Cur(cur)

        async def executescript(self, script):
            raw.executescript(script)

        async def commit(self):
            raw.commit()

        async def close(self):
            raw.close()

    return _Conn(), raw


def _make_user(uid: int, username: str = "user", first_name: str = "User"):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.first_name = first_name
    u.last_name = ""
    u.language_code = "id"
    u.is_premium = False
    u.is_bot = False
    return u


def _make_update(user, text: str = "", chat_type: str = "private", chat_id: int | None = None):
    up = MagicMock()
    up.effective_user = user
    chat = MagicMock()
    chat.type = chat_type
    chat.id = chat_id if chat_id is not None else (user.id if chat_type == "private" else -100777888)
    up.effective_chat = chat

    msg = MagicMock()
    msg.text = text
    msg.chat_id = chat.id
    msg.from_user = user
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    status_msg.reply_text = AsyncMock()
    msg.reply_text = AsyncMock(return_value=status_msg)

    up.message = msg
    up.effective_message = msg
    up.callback_query = None
    return up, status_msg


def _make_context(db, conn, args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.bot_data = {"db": db, "conn": conn}
    ctx.application = MagicMock()
    ctx.application.bot_data = {"db": db, "conn": conn}
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.forward_message = AsyncMock(return_value=MagicMock())
    ctx.bot.forward_messages = AsyncMock(return_value=[MagicMock()])
    return ctx


async def _seed_user(db: Database, conn, uid: int, username: str, first_name: str, role: str = ROLE_PUBLIC):
    await db.upsert_user_from_telegram(
        conn,
        telegram_id=uid,
        username=username,
        first_name=first_name,
        last_name="",
        language_code="id",
        is_premium=False,
        is_bot=False,
        raw_profile={},
    )
    if role != ROLE_PUBLIC:
        await db.set_role(conn, uid, role)


# =============================================================================
# 1. E2E FLOW: /link_kerja -> OTP -> /pfp -> AGRA -> /pfp daily & weekly
# =============================================================================


@pytest.mark.asyncio
async def test_e2e_akun_kerja_pfp_single_range_and_stats():
    promo.OTP_STORE.clear()
    conn, raw = _make_sqlite_conn()
    db = Database()

    main_uid = 1001
    work1_uid = 2001
    work2_uid = 2002
    await _seed_user(db, conn, main_uid, "alice_main", "Alice", ROLE_STUDENT)
    await _seed_user(db, conn, work1_uid, "alice_work1", "WorkOne", ROLE_PUBLIC)
    await _seed_user(db, conn, work2_uid, "alice_work2", "WorkTwo", ROLE_PUBLIC)

    # Set stuck onboarding_step on work1 to verify linking clears it
    await db.set_onboarding_step(conn, work1_uid, "WAIT_ACCESS_CODE")

    main_user = _make_user(main_uid, "alice_main", "Alice")
    work1_user = _make_user(work1_uid, "alice_work1", "WorkOne")
    work2_user = _make_user(work2_uid, "alice_work2", "WorkTwo")

    # 1) Main account generates 2 OTPs and links work1 & work2
    for w_user in (work1_user, work2_user):
        up_link, _ = _make_update(main_user, "/link_kerja")
        ctx_link = _make_context(db, conn)
        await promo.link_kerja_cmd(up_link, ctx_link)
        reply_otp = up_link.message.reply_text.call_args[0][0]
        m = re.search(r"KERJA-[A-Z0-9]{6}", reply_otp)
        assert m is not None
        otp_code = m.group(0)

        up_otp, _ = _make_update(w_user, f"  {otp_code.lower()}  ")
        ctx_otp = _make_context(db, conn)
        await promo.handle_otp_message(up_otp, ctx_otp)
        assert "Berhasil" in up_otp.message.reply_text.call_args[0][0]
        assert up_otp.message.reply_text.call_args[1]["parse_mode"] == "HTML"
        ctx_otp.bot.send_message.assert_awaited_once()

    # Check work1 onboarding_step was cleared
    w1_row = await db.get_user(conn, work1_uid)
    assert w1_row["onboarding_step"] is None

    # 2) work1 runs /pfp single post in private DM
    up_pfp1, st1 = _make_update(work1_user, "/pfp https://t.me/partner_ch/50")
    ctx_pfp1 = _make_context(db, conn, args=["https://t.me/partner_ch/50"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_pfp1, ctx_pfp1)

    edit1 = st1.edit_text.call_args[0][0]
    assert "+1 Agra" in edit1
    assert f"Akun Utama (<code>{main_uid}</code>)" in edit1
    assert await db.agra_total(conn, main_uid) == 1
    assert await db.agra_total(conn, work1_uid) == 0

    # 3) work2 runs /pfp range (5 posts) in private DM
    up_pfp2, st2 = _make_update(work2_user, "/pfp https://t.me/partner_ch/60 to https://t.me/partner_ch/64")
    ctx_pfp2 = _make_context(db, conn, args=["https://t.me/partner_ch/60", "to", "https://t.me/partner_ch/64"])
    ctx_pfp2.bot.forward_messages = AsyncMock(return_value=[MagicMock()] * 5)
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_pfp2, ctx_pfp2)

    edit2 = st2.edit_text.call_args[0][0]
    assert "+5 Agra" in edit2
    assert await db.agra_total(conn, main_uid) == 6
    assert await db.agra_total(conn, work2_uid) == 0

    # 4) Verify agra_ledger records actor_id and target_id accurately
    ledger_rows = await (await conn.execute("SELECT * FROM agra_ledger ORDER BY id ASC")).fetchall()
    assert len(ledger_rows) == 2
    assert ledger_rows[0]["target_telegram_id"] == main_uid
    assert ledger_rows[0]["actor_telegram_id"] == work1_uid
    assert "Akun Kerja" in ledger_rows[0]["description"]
    assert ledger_rows[1]["target_telegram_id"] == main_uid
    assert ledger_rows[1]["actor_telegram_id"] == work2_uid

    # 5) Verify pfp_logs & /pfp daily & /pfp weekly aggregate under Main Account (Alice)
    daily_text, _ = await pfp.get_pfp_daily_content(conn, db)
    assert "<b>Alice</b> (@alice_main) — <b>6</b> post (2x fwd)" in daily_text
    assert "Total Pengguna:</b> 1 orang" in daily_text
    assert "Total Post Ter-forward:</b> 6 post" in daily_text
    assert "WorkOne" not in daily_text
    assert "WorkTwo" not in daily_text

    weekly_text, _ = await pfp.get_pfp_weekly_content(conn, db)
    assert "Total Pengguna Unik:</b> 1 orang" in weekly_text
    assert "Total Seluruh Post:</b> 6 post" in weekly_text

    await conn.close()


# =============================================================================
# 2. PRIVACY IN GROUPS & TUTORIAL STATUS
# =============================================================================


@pytest.mark.asyncio
async def test_akun_kerja_pfp_group_privacy_and_tutor_status():
    conn, raw = _make_sqlite_conn()
    db = Database()
    main_uid = 1010
    work_uid = 2010
    await _seed_user(db, conn, main_uid, "secret_main", "SecretMain", ROLE_STUDENT)
    await _seed_user(db, conn, work_uid, "public_work", "PublicWork", ROLE_PUBLIC)
    assert await db.add_linked_account(conn, main_uid, work_uid) is True

    work_user = _make_user(work_uid, "public_work", "PublicWork")

    # Group /pfp must NOT expose main_uid in reply
    up_grp, st_grp = _make_update(work_user, "/pfp https://t.me/pub_ch/77", chat_type="supergroup", chat_id=-100999)
    ctx_grp = _make_context(db, conn, args=["https://t.me/pub_ch/77"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_grp, ctx_grp)

    grp_reply = st_grp.edit_text.call_args[0][0]
    assert "+1 Agra" in grp_reply
    assert "Akun Utama tertaut" in grp_reply
    assert str(main_uid) not in grp_reply
    assert "secret_main" not in grp_reply
    assert await db.agra_total(conn, main_uid) == 1

    # /pfp without args on work account shows Status Akun Kerja
    up_tutor, _ = _make_update(work_user, "/pfp")
    ctx_tutor = _make_context(db, conn, args=[])
    with patch("bot.handlers.pfp.is_owner", return_value=False):
        await pfp.cmd_pfp(up_tutor, ctx_tutor)
    tutor_text = up_tutor.effective_message.reply_text.call_args[0][0]
    assert "Status Akun Kerja" in tutor_text
    assert "Sub Menu Khusus Owner" not in tutor_text

    await conn.close()


# =============================================================================
# 3. CROSS-ACCOUNT DUPLICATE PROTECTION & CONCURRENCY LOCK
# =============================================================================


@pytest.mark.asyncio
async def test_cross_account_duplicate_kloter_and_subset_blocking():
    conn, raw = _make_sqlite_conn()
    db = Database()
    main_uid = 1020
    work_uid = 2020
    await _seed_user(db, conn, main_uid, "main20", "Main20", ROLE_STUDENT)
    await _seed_user(db, conn, work_uid, "work20", "Work20", ROLE_PUBLIC)

    # Pre-link forward by work_uid in same kloter
    work_user = _make_user(work_uid, "work20", "Work20")
    main_user = _make_user(main_uid, "main20", "Main20")

    up_pre, _ = _make_update(work_user, "/pfp https://t.me/ch_pre/5")
    ctx_pre = _make_context(db, conn, args=["https://t.me/ch_pre/5"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_pre, ctx_pre)
    assert await db.agra_total(conn, work_uid) == 1

    # Now link work_uid -> main_uid
    assert await db.add_linked_account(conn, main_uid, work_uid) is True

    # Work account tries same pre-link post again -> blocked!
    up_pre_dup, _ = _make_update(work_user, "/pfp https://t.me/ch_pre/5")
    ctx_pre_dup = _make_context(db, conn, args=["https://t.me/ch_pre/5"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_pre_dup, ctx_pre_dup)
    assert "sudah pernah Anda forward" in up_pre_dup.effective_message.reply_text.call_args[0][0]
    assert ctx_pre_dup.bot.forward_message.await_count == 0

    # Main account forwards range 10..15 (all 6 succeed)
    up_rng, _ = _make_update(main_user, "/pfp https://t.me/ch_x/10 to https://t.me/ch_x/15")
    ctx_rng = _make_context(db, conn, args=["https://t.me/ch_x/10", "to", "https://t.me/ch_x/15"])
    ctx_rng.bot.forward_messages = AsyncMock(return_value=[MagicMock()] * 6)
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_rng, ctx_rng)
    assert await db.agra_total(conn, main_uid) == 6

    # Work account tries exact 10..15 -> blocked!
    up_dup1, _ = _make_update(work_user, "/pfp https://t.me/ch_x/10 to https://t.me/ch_x/15")
    ctx_dup1 = _make_context(db, conn, args=["https://t.me/ch_x/10", "to", "https://t.me/ch_x/15"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_dup1, ctx_dup1)
    assert "sudah pernah Anda forward" in up_dup1.effective_message.reply_text.call_args[0][0]

    # Work account tries subset single post 12 -> blocked!
    up_dup2, _ = _make_update(work_user, "/pfp https://t.me/ch_x/12")
    ctx_dup2 = _make_context(db, conn, args=["https://t.me/ch_x/12"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_dup2, ctx_dup2)
    assert "sudah pernah Anda forward" in up_dup2.effective_message.reply_text.call_args[0][0]
    assert await db.agra_total(conn, main_uid) == 6

    # Partial range failure: 20..22 where 21 fails -> retrying single 21 IS allowed!
    up_part, _ = _make_update(work_user, "/pfp https://t.me/ch_part/20 to https://t.me/ch_part/22")
    ctx_part = _make_context(db, conn, args=["https://t.me/ch_part/20", "to", "https://t.me/ch_part/22"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), \
         patch("bot.handlers.pfp.POST_CH_ID", -100222), \
         patch("bot.handlers.pfp.forward_posts_to_keep", AsyncMock(return_value=(2, None))):
        await pfp.cmd_pfp(up_part, ctx_part)
    assert await db.agra_total(conn, main_uid) == 8

    up_retry, _ = _make_update(main_user, "/pfp https://t.me/ch_part/21")
    ctx_retry = _make_context(db, conn, args=["https://t.me/ch_part/21"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_retry, ctx_retry)
    assert await db.agra_total(conn, main_uid) == 9

    await conn.close()


@pytest.mark.asyncio
async def test_cross_account_concurrency_lock_blocks_parallel_request():
    conn, raw = _make_sqlite_conn()
    db = Database()
    main_uid = 1030
    work_uid = 2030
    await _seed_user(db, conn, main_uid, "main30", "Main30", ROLE_STUDENT)
    await _seed_user(db, conn, work_uid, "work30", "Work30", ROLE_PUBLIC)
    assert await db.add_linked_account(conn, main_uid, work_uid) is True

    work_user = _make_user(work_uid, "work30", "Work30")
    main_user = _make_user(main_uid, "main30", "Main30")

    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_forward(*args, **kwargs):
        started.set()
        await proceed.wait()
        return 1, None

    up_w, _ = _make_update(work_user, "/pfp https://t.me/ch_lock/1")
    ctx_w = _make_context(db, conn, args=["https://t.me/ch_lock/1"])

    up_m, _ = _make_update(main_user, "/pfp https://t.me/ch_lock/2")
    ctx_m = _make_context(db, conn, args=["https://t.me/ch_lock/2"])

    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), \
         patch("bot.handlers.pfp.POST_CH_ID", -100222), \
         patch("bot.handlers.pfp.forward_posts_to_keep", side_effect=slow_forward):
        t_work = asyncio.create_task(pfp.cmd_pfp(up_w, ctx_w))
        await started.wait()
        await pfp.cmd_pfp(up_m, ctx_m)
        proceed.set()
        await t_work

    busy_reply = up_m.effective_message.reply_text.call_args[0][0]
    assert "masih diproses" in busy_reply
    assert await db.agra_total(conn, main_uid) == 1

    await conn.close()


# =============================================================================
# 4. SECURITY: NO PRIVILEGE ESCALATION & LINKING INTEGRITY
# =============================================================================


@pytest.mark.asyncio
async def test_work_account_does_not_inherit_owner_or_pfp_admin_privileges():
    conn, raw = _make_sqlite_conn()
    db = Database()
    owner_uid = 90001
    staff_pfp_uid = 90002
    work_owner_uid = 90101
    work_staff_uid = 90102

    await _seed_user(db, conn, owner_uid, "owner_u", "Owner", ROLE_OWNER)
    await _seed_user(db, conn, staff_pfp_uid, "pfp_u", "PFPStaff", ROLE_INTERNAL)
    await db.set_profile_partial(conn, staff_pfp_uid, {"position_detail": ["d_pfp"]})
    await _seed_user(db, conn, work_owner_uid, "work_own", "WorkOwner", ROLE_PUBLIC)
    await _seed_user(db, conn, work_staff_uid, "work_pfp", "WorkPFP", ROLE_PUBLIC)

    await db.add_linked_account(conn, owner_uid, work_owner_uid)
    await db.add_linked_account(conn, staff_pfp_uid, work_staff_uid)

    with patch("bot.handlers.pfp.is_owner", side_effect=lambda u: u == owner_uid), \
         patch("bot.handlers.pfp.is_admin_elevated", return_value=False):
        assert await pfp.is_authorized_pfp_admin(conn, db, work_owner_uid) is False
        assert await pfp.is_authorized_pfp_admin(conn, db, work_staff_uid) is False

        for target_w in (work_owner_uid, work_staff_uid):
            w_user = _make_user(target_w, f"w{target_w}", "W")
            for sub in ("daily", "weekly", "post"):
                up, _ = _make_update(w_user, f"/pfp {sub}")
                ctx = _make_context(db, conn, args=[sub])
                await pfp.cmd_pfp(up, ctx)
                msg = up.effective_message.reply_text.call_args[0][0].lower()
                assert "owner" in msg or "tidak memiliki izin" in msg

            # Direct /post_keep blocked
            up_pk, _ = _make_update(w_user, "/post_keep")
            ctx_pk = _make_context(db, conn)
            await pfp.cmd_post_keep(up_pk, ctx_pk)
            assert "tidak memiliki izin" in up_pk.effective_message.reply_text.call_args[0][0].lower()

            # Callback queries blocked
            for cb_data in ("pfp:daily", "pfp:weekly", "pfp:post"):
                up_cb = MagicMock()
                up_cb.effective_user = w_user
                up_cb.callback_query = MagicMock()
                up_cb.callback_query.data = cb_data
                up_cb.callback_query.answer = AsyncMock()
                await pfp.cb_pfp(up_cb, _make_context(db, conn))
                assert up_cb.callback_query.answer.call_args[1]["show_alert"] is True

    await conn.close()


@pytest.mark.asyncio
async def test_linking_integrity_blocks_multi_main_cycles_and_missing_fk():
    promo.OTP_STORE.clear()
    conn, raw = _make_sqlite_conn(enable_fk=True)
    db = Database()

    main_a = 1040
    main_b = 1041
    work_w = 2040
    unreg_main = 1049  # Not yet in users table!
    unreg_work = 2049  # Not yet in users table!

    await _seed_user(db, conn, main_a, "main_a", "MainA", ROLE_STUDENT)
    await _seed_user(db, conn, main_b, "main_b", "MainB", ROLE_STUDENT)
    await _seed_user(db, conn, work_w, "work_w", "WorkW", ROLE_PUBLIC)

    # 1) Self-link rejected and OTP remains valid for real work account
    u_a = _make_user(main_a, "main_a", "MainA")
    u_b = _make_user(main_b, "main_b", "MainB")
    u_w = _make_user(work_w, "work_w", "WorkW")

    up_l1, _ = _make_update(u_a, "/link_kerja")
    await promo.link_kerja_cmd(up_l1, _make_context(db, conn))
    otp_a = re.search(r"KERJA-[A-Z0-9]{6}", up_l1.message.reply_text.call_args[0][0]).group(0)

    up_self, _ = _make_update(u_a, otp_a)
    await promo.handle_otp_message(up_self, _make_context(db, conn))
    assert "akun utama yang sama" in up_self.message.reply_text.call_args[0][0]
    assert otp_a in promo.OTP_STORE  # Not burned!

    # Now work_w links to main_a
    up_w_otp, _ = _make_update(u_w, otp_a)
    await promo.handle_otp_message(up_w_otp, _make_context(db, conn))
    assert "Berhasil" in up_w_otp.message.reply_text.call_args[0][0]
    assert otp_a not in promo.OTP_STORE  # Consumed!

    # 2) Multi-main blocked: main_b cannot steal work_w
    up_l2, _ = _make_update(u_b, "/link_kerja")
    await promo.link_kerja_cmd(up_l2, _make_context(db, conn))
    otp_b = re.search(r"KERJA-[A-Z0-9]{6}", up_l2.message.reply_text.call_args[0][0]).group(0)

    up_steal, _ = _make_update(u_w, otp_b)
    await promo.handle_otp_message(up_steal, _make_context(db, conn))
    assert "milik akun utama lain" in up_steal.message.reply_text.call_args[0][0]
    assert await db.get_main_account_by_linked(conn, work_w) == main_a

    # 3) Chain blocked: work_w cannot generate /link_kerja
    up_chain_cmd, _ = _make_update(u_w, "/link_kerja")
    await promo.link_kerja_cmd(up_chain_cmd, _make_context(db, conn))
    assert "Sudah Menjadi Akun Kerja" in up_chain_cmd.message.reply_text.call_args[0][0]

    # 4) Cycle blocked: main_a (who already owns work_w) cannot send main_b's OTP to become work account
    up_cycle, _ = _make_update(u_a, otp_b)
    await promo.handle_otp_message(up_cycle, _make_context(db, conn))
    assert "memiliki Akun Kerja sendiri" in up_cycle.message.reply_text.call_args[0][0]

    # 5) Unregistered users calling /link_kerja + OTP auto-create rows without FK crash
    u_unreg_m = _make_user(unreg_main, "unreg_m", "UnregM")
    u_unreg_w = _make_user(unreg_work, "unreg_w", "UnregW")
    up_um, _ = _make_update(u_unreg_m, "/link_kerja")
    await promo.link_kerja_cmd(up_um, _make_context(db, conn))
    otp_unreg = re.search(r"KERJA-[A-Z0-9]{6}", up_um.message.reply_text.call_args[0][0]).group(0)

    up_uw, _ = _make_update(u_unreg_w, otp_unreg)
    await promo.handle_otp_message(up_uw, _make_context(db, conn))
    assert "Berhasil" in up_uw.message.reply_text.call_args[0][0]
    assert await db.get_main_account_by_linked(conn, unreg_work) == unreg_main

    await conn.close()


@pytest.mark.asyncio
async def test_legacy_broken_linked_accounts_safe_fallback():
    """Verify resolve_pfp_credit_user_id safely falls back if legacy DB has orphan main_id or cycle."""
    conn, raw = _make_sqlite_conn(enable_fk=False)
    db = Database()
    await _seed_user(db, conn, 5001, "u5001", "U5001", ROLE_PUBLIC)
    await _seed_user(db, conn, 5002, "u5002", "U5002", ROLE_PUBLIC)
    await _seed_user(db, conn, 5003, "u5003", "U5003", ROLE_PUBLIC)

    # Case 1: Orphan main_id (999999 not in users)
    await db.add_linked_account(conn, 999999, 5001)
    cid1, is_w1 = await pfp.resolve_pfp_credit_user_id(conn, db, 5001)
    assert cid1 == 5001 and is_w1 is False

    # Case 2: Legacy cycle 5002 <-> 5003
    await db.add_linked_account(conn, 5002, 5003)
    await db.add_linked_account(conn, 5003, 5002)
    cid2, is_w2 = await pfp.resolve_pfp_credit_user_id(conn, db, 5002)
    assert cid2 == 5002 and is_w2 is False

    await conn.close()


# =============================================================================
# 5. UNLINK WORKFLOW & IDOR PROTECTION
# =============================================================================


@pytest.mark.asyncio
async def test_cek_and_unlink_kerja_main_self_and_idor():
    conn, raw = _make_sqlite_conn()
    db = Database()
    main_uid = 1050
    work_uid = 2050
    stranger_uid = 3050
    await _seed_user(db, conn, main_uid, "main50", "Main50", ROLE_STUDENT)
    await _seed_user(db, conn, work_uid, "work50", "Work50", ROLE_PUBLIC)
    await _seed_user(db, conn, stranger_uid, "stranger", "Stranger", ROLE_PUBLIC)
    await db.add_linked_account(conn, main_uid, work_uid)

    u_main = _make_user(main_uid, "main50", "Main50")
    u_work = _make_user(work_uid, "work50", "Work50")
    u_stranger = _make_user(stranger_uid, "stranger", "Stranger")

    # 1) /cek_akun_kerja from Main Account shows label + unlink button
    up_cm, _ = _make_update(u_main, "/cek_akun_kerja")
    await promo.cek_akun_kerja_cmd(up_cm, _make_context(db, conn))
    cm_text = up_cm.message.reply_text.call_args[0][0]
    cm_kb = up_cm.message.reply_text.call_args[1]["reply_markup"]
    assert str(work_uid) in cm_text and "@work50" in cm_text and "/pfp" in cm_text
    assert cm_kb.inline_keyboard[0][0].callback_data == f"unlink_kerja:main:{work_uid}"

    # 2) /cek_akun_kerja from Work Account shows Main Account + self-unlink button
    up_cw, _ = _make_update(u_work, "/cek_akun_kerja")
    await promo.cek_akun_kerja_cmd(up_cw, _make_context(db, conn))
    cw_text = up_cw.message.reply_text.call_args[0][0]
    cw_kb = up_cw.message.reply_text.call_args[1]["reply_markup"]
    assert "Status Akun Kerja" in cw_text and str(main_uid) in cw_text
    assert cw_kb.inline_keyboard[0][0].callback_data == f"unlink_kerja:self:{main_uid}"

    # 3) IDOR: Stranger tries callback unlink_kerja:main:2050 -> fails cleanly!
    up_idor = MagicMock()
    up_idor.effective_user = u_stranger
    up_idor.effective_chat = MagicMock(type="private", id=stranger_uid)
    up_idor.callback_query = MagicMock()
    up_idor.callback_query.data = f"unlink_kerja:main:{work_uid}"
    up_idor.callback_query.answer = AsyncMock()
    up_idor.callback_query.edit_message_text = AsyncMock()
    await promo.unlink_kerja_callback(up_idor, _make_context(db, conn))
    assert await db.get_main_account_by_linked(conn, work_uid) == main_uid

    # 4) Work account self-unlinks via callback
    up_self_cb = MagicMock()
    up_self_cb.effective_user = u_work
    up_self_cb.effective_chat = MagicMock(type="private", id=work_uid)
    up_self_cb.callback_query = MagicMock()
    up_self_cb.callback_query.data = f"unlink_kerja:self:{main_uid}"
    up_self_cb.callback_query.answer = AsyncMock()
    up_self_cb.callback_query.edit_message_text = AsyncMock()
    ctx_cb = _make_context(db, conn)
    await promo.unlink_kerja_callback(up_self_cb, ctx_cb)
    assert await db.get_main_account_by_linked(conn, work_uid) is None
    assert "berhasil diputuskan" in up_self_cb.callback_query.edit_message_text.call_args[0][0]

    # 5) Re-link and test /unlink_kerja @username command from Main Account
    await db.add_linked_account(conn, main_uid, work_uid)
    up_ul, _ = _make_update(u_main, "/unlink_kerja @work50")
    await promo.unlink_kerja_cmd(up_ul, _make_context(db, conn, args=["@work50"]))
    assert "berhasil diputuskan" in up_ul.message.reply_text.call_args[0][0]
    assert await db.get_main_account_by_linked(conn, work_uid) is None

    # After unlink, work_uid /pfp credits work_uid itself again
    up_after, _ = _make_update(u_work, "/pfp https://t.me/ch_after/9")
    ctx_after = _make_context(db, conn, args=["https://t.me/ch_after/9"])
    with patch("bot.handlers.pfp.KEEP_CH_ID", -100111), patch("bot.handlers.pfp.POST_CH_ID", -100222):
        await pfp.cmd_pfp(up_after, ctx_after)
    assert await db.agra_total(conn, work_uid) == 1
    assert await db.agra_total(conn, main_uid) == 0

    await conn.close()


# =============================================================================
# 6. QUERY PLAN (TURSO INDEX VERIFICATION) & HANDLER REGISTRATION
# =============================================================================


def test_turso_query_plans_for_akun_kerja_use_indexes():
    raw = sqlite3.connect(":memory:")
    raw.executescript(SCHEMA)

    queries = {
        "linked_main_lookup": (
            "SELECT main_user_id FROM linked_accounts WHERE promo_user_id = ? ORDER BY created_at ASC, main_user_id ASC LIMIT 1",
            (2001,),
        ),
        "pfp_dup_single_uid": (
            "SELECT id FROM pfp_logs WHERE user_id = ? AND created_at > ? AND channel_id = ? "
            "AND ((first_msg_id = ? AND last_msg_id = ?) OR (first_msg_id <= ? AND last_msg_id >= ? AND forwarded_count >= (last_msg_id - first_msg_id + 1))) LIMIT 1",
            (1001, 1.0, "@ch", 1, 1, 1, 1),
        ),
        "pfp_dup_work_in_uids": (
            "SELECT id FROM pfp_logs WHERE user_id IN (?, ?) AND created_at > ? AND channel_id = ? "
            "AND ((first_msg_id = ? AND last_msg_id = ?) OR (first_msg_id <= ? AND last_msg_id >= ? AND forwarded_count >= (last_msg_id - first_msg_id + 1))) LIMIT 1",
            (1001, 2001, 1.0, "@ch", 1, 1, 1, 1),
        ),
    }

    for name, (sql, params) in queries.items():
        plan = " ".join(str(r) for r in raw.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall())
        assert "SCAN linked_accounts" not in plan, f"Full table scan in {name}: {plan}"
        assert "SCAN pfp_logs" not in plan, f"Full table scan in {name}: {plan}"
        assert "USING INDEX" in plan, f"Expected index usage in {name}: {plan}"

    raw.close()


def test_handlers_registered_cleanly():
    app = Application.builder().token("123456:TESTTOKEN").build()
    setup_handlers(app, Database())
    grp0 = app.handlers.get(0, [])
    cmds = {c for h in grp0 if isinstance(h, CommandHandler) for c in h.commands}
    assert {"link_kerja", "cek_akun_kerja", "unlink_kerja", "pfp"}.issubset(cmds)
    cb_patterns = [str(getattr(h.pattern, "pattern", "")) for h in grp0 if isinstance(h, CallbackQueryHandler)]
    assert "^unlink_kerja:" in cb_patterns
    assert "^pfp:" in cb_patterns
