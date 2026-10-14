import asyncio
import os
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram import Update, Message, User, Chat, PhotoSize
from bot.database import Database, ROLE_INTERNAL, ROLE_PUBLIC, ROLE_OWNER, ROLE_ADMIN
from bot.handlers import kontrak

def create_mock_update(user_id=1073487310, text="", is_group=False, photos=None):
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "Tester"
    user.last_name = "Staff"
    user.username = f"tester_{user_id}"
    update.effective_user = user
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = user_id if not is_group else -10099999
    update.effective_chat.type = "private" if not is_group else "supergroup"
    
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.message_id = 1001
    msg.reply_text = AsyncMock()
    msg.reply_photo = AsyncMock()
    msg.delete = AsyncMock()
    msg.chat_id = update.effective_chat.id
    msg.photo = photos or []
    update.effective_message = msg
    update.message = msg
    return update

def create_mock_context(db, conn, args=None):
    context = MagicMock()
    context.application = MagicMock()
    context.application.bot_data = {"db": db, "conn": conn}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.get_file = AsyncMock()
    context.args = args or []
    return context

@pytest.mark.asyncio
async def test_qa_kontrak_full_lifecycle_and_security():
    os.environ["TURSO_DATABASE_URL"] = "file:test_kontrak_qa.sqlite3"
    if os.path.exists("test_kontrak_qa.sqlite3"):
        os.remove("test_kontrak_qa.sqlite3")

    db = Database()
    conn = await db.connect()

    try:
        await conn.execute("DELETE FROM users WHERE telegram_id IN (888111, 999111)")
        await conn.commit()

        # Mock download photo bytes
        with patch.object(kontrak, "_download_telegram_photo", new=AsyncMock(return_value=b"fake_ttd_bytes")):
            # 1. Security Gate: Public user cannot use /kontrak
            uid_pub = 888111
            await db.upsert_user_from_telegram(
                conn, telegram_id=uid_pub, username="pub_user", first_name="Public", last_name="",
                language_code="id", is_premium=False, is_bot=False, raw_profile={}
            )
            u = create_mock_update(user_id=uid_pub, text="/kontrak")
            c = create_mock_context(db, conn)
            await kontrak.cmd_kontrak_router(u, c)
            u.message.reply_text.assert_called_with("Fitur kontrak hanya untuk staf internal.")

            # 2. Onboarding Staf Baru: Masuk sebagai internal
            uid_staff = 999111
            await db.upsert_user_from_telegram(
                conn, telegram_id=uid_staff, username="staff_user", first_name="Staff", last_name="Baru",
                language_code="id", is_premium=False, is_bot=False, raw_profile={}
            )
            await db.set_role(conn, uid_staff, ROLE_INTERNAL)
            await db.set_profile_partial(conn, uid_staff, {"full_name": "Staff Baru", "position_detail": ["dosen"]})

            # Check /kontrak saya sebelum ada TTD
            u = create_mock_update(user_id=uid_staff, text="/kontrak saya")
            c = create_mock_context(db, conn, args=["saya"])
            await kontrak.cmd_kontrak_router(u, c)
            call_text = u.message.reply_text.call_args[0][0]
            assert "Tanda tangan belum tersedia" in call_text

            # Mulai /kontrak ttd
            u = create_mock_update(user_id=uid_staff, text="/kontrak ttd")
            c = create_mock_context(db, conn, args=["ttd"])
            await kontrak.cmd_kontrak_router(u, c)
            row = await db.get_user(conn, uid_staff)
            assert row["onboarding_step"] == kontrak.STEP_KONTRAK_TTD

            # Upload foto TTD
            photo_mock = MagicMock(spec=PhotoSize)
            photo_mock.file_id = "ttd_photo_file_id_1"
            u_photo = create_mock_update(user_id=uid_staff, photos=[photo_mock])
            await kontrak.on_kontrak_ttd(u_photo, c)
            call_text = u_photo.message.reply_text.call_args[0][0]
            assert "Tanda tangan berhasil disimpan!" in call_text
            assert "Silakan ketik <code>/kontrak saya</code>" in call_text

            # Cek status user: belum punya kontrak resmi
            row = await db.get_user(conn, uid_staff)
            prof = json.loads(row["profile_json"])
            assert prof.get("contract_seq_no") is None
            assert prof.get("contract_end_ts") is None
            assert prof.get("ttd_file_id") == "ttd_photo_file_id_1"

            # Buka /kontrak saya -> draf preview
            u = create_mock_update(user_id=uid_staff, text="/kontrak saya")
            c = create_mock_context(db, conn, args=["saya"])
            await kontrak.cmd_kontrak_router(u, c)
            # Harus mengirim foto draf dengan reply_markup
            assert u.message.reply_photo.called
            cap = u.message.reply_photo.call_args[1]["caption"]
            assert "Draf Kontrak Kerja Staf Baru" in cap
            assert "/kontrak sahkan" in cap

            # Sahkan kontrak via /kontrak sahkan
            u = create_mock_update(user_id=uid_staff, text="/kontrak sahkan")
            c = create_mock_context(db, conn, args=["sahkan"])
            await kontrak.cmd_kontrak_router(u, c)
            
            # Verifikasi di database setelah sahkan
            row = await db.get_user(conn, uid_staff)
            prof = json.loads(row["profile_json"])
            seq_1 = prof.get("contract_seq_no")
            assert seq_1 is not None
            assert prof.get("contract_count") == 1
            assert prof.get("internal_since") is not None
            assert len(prof.get("contract_history")) == 1
            assert prof.get("contract_history")[0]["iteration"] == 1
            start_str_1 = prof.get("contract_start")
            end_str_1 = prof.get("contract_end")

            # 3. Ganti TTD saat kontrak sedang aktif
            # Staf lama ubah TTD
            await db.set_onboarding_step(conn, uid_staff, kontrak.STEP_KONTRAK_TTD)
            photo_mock_2 = MagicMock(spec=PhotoSize)
            photo_mock_2.file_id = "ttd_photo_file_id_2_new"
            u_photo_2 = create_mock_update(user_id=uid_staff, photos=[photo_mock_2])
            await kontrak.on_kontrak_ttd(u_photo_2, c)
            call_text = u_photo_2.message.reply_text.call_args[0][0]
            assert "Tanda tangan berhasil diperbarui!" in call_text
            assert "tidak mengubah masa berlaku" in call_text

            # Verifikasi tanggal kontrak dan seq_no TIDAK BERUBAH
            row = await db.get_user(conn, uid_staff)
            prof = json.loads(row["profile_json"])
            assert prof.get("contract_seq_no") == seq_1
            assert prof.get("contract_start") == start_str_1
            assert prof.get("contract_end") == end_str_1
            assert prof.get("ttd_file_id") == "ttd_photo_file_id_2_new"

            # 4. Uji Guard /kontrak renew
            # Saat kontrak masih aktif (> 7 hari), renew harus diblokir
            u = create_mock_update(user_id=uid_staff, text="/kontrak renew")
            c = create_mock_context(db, conn, args=["renew"])
            await kontrak.cmd_kontrak_router(u, c)
            call_text = u.message.reply_text.call_args[0][0]
            assert "Kontrak Anda masih aktif" in call_text
            assert "H-7" in call_text

            # Simulasikan masa kontrak masuk H-3 (expiring)
            now_ts = time.time()
            expiring_end_ts = now_ts + (3 * 86400)
            await db.set_profile_partial(conn, uid_staff, {"contract_end_ts": expiring_end_ts})

            # Sekarang jalankan /kontrak renew
            u = create_mock_update(user_id=uid_staff, text="/kontrak renew")
            c = create_mock_context(db, conn, args=["renew"])
            await kontrak.cmd_kontrak_router(u, c)

            # Verifikasi hasil renew:
            row = await db.get_user(conn, uid_staff)
            prof = json.loads(row["profile_json"])
            # Nomor surat / ID seq harus tetap sama persis!
            assert prof.get("contract_seq_no") == seq_1
            # Contract count bertambah jadi 2
            assert prof.get("contract_count") == 2
            # Riwayat bertambah menjadi 2 entri
            assert len(prof.get("contract_history")) == 2
            assert prof.get("contract_history")[1]["iteration"] == 2

            # 5. Uji Admin Tools (/kontrak all dan /kontrak check)
            uid_admin = 777111
            await db.upsert_user_from_telegram(
                conn, telegram_id=uid_admin, username="admin_user", first_name="Admin", last_name="",
                language_code="id", is_premium=False, is_bot=False, raw_profile={}
            )
            await db.set_role(conn, uid_admin, ROLE_ADMIN)

            # Test /kontrak all
            u = create_mock_update(user_id=uid_admin, text="/kontrak all")
            c = create_mock_context(db, conn, args=["all"])
            await kontrak.cmd_kontrak_router(u, c)
            all_text = u.message.reply_text.call_args[0][0]
            assert f"[ID: {seq_1:04d}]" in all_text
            assert "Ke-2" in all_text
            assert "Sejak" in all_text

            # Test /kontrak check by contract ID
            u = create_mock_update(user_id=uid_admin, text=f"/kontrak check {seq_1}")
            c = create_mock_context(db, conn, args=["check", str(seq_1)])
            await kontrak.cmd_kontrak_router(u, c)
            assert u.message.reply_photo.called
            check_text = u.message.reply_text.call_args[0][0]
            assert "Detail Informasi Kontrak Staf" in check_text
            assert f"[ID: {seq_1:04d}]" in check_text
            assert "Riwayat Penandatanganan Kontrak" in check_text
            assert "1." in check_text
            assert "2." in check_text
    finally:
        await conn.close()
        if os.path.exists("test_kontrak_qa.sqlite3"):
            os.remove("test_kontrak_qa.sqlite3")
