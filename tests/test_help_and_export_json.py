"""
Test Suite: Verify /help, /help_owner, and graduation ZIP JSON inclusion.
1. Owner /help is identical to Admin view, plus /help_owner hint.
2. /help_owner is owner-only and contains comprehensive owner command guide.
3. /export_kelulusan zip packages the JSON archive inside the zip file.
"""

import asyncio
import inspect
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.database import Database, ROLE_OWNER, ROLE_ADMIN, ROLE_STUDENT, ROLE_PUBLIC
from bot.settings import OWNER_ID
from bot.handlers import commands, graduation
from bot.graduation_excel import StudentGraduationData, CourseGrade, ClubGrade
from telegram import Update, Message, User, Chat


def run_sync(coro):
    stack = [coro]
    val = None
    exc = None
    while stack:
        top = stack[-1]
        try:
            if exc:
                curr_exc = exc
                exc = None
                res = top.throw(curr_exc)
            else:
                res = top.send(val)
                val = None
            if inspect.iscoroutine(res):
                stack.append(res)
            elif res is None:
                pass
            else:
                val = res
        except StopIteration as e:
            stack.pop()
            val = e.value
        except Exception as e:
            stack.pop()
            exc = e
    if exc:
        raise exc
    return val


def make_mock_user(uid: int, username: str = "tester", first_name: str = "Test"):
    u = MagicMock(spec=User)
    u.id = uid
    u.username = username
    u.first_name = first_name
    u.last_name = ""
    return u


def make_mock_update(user: User, text: str = ""):
    up = MagicMock(spec=Update)
    up.effective_user = user
    chat = MagicMock(spec=Chat)
    chat.id = user.id
    chat.type = "private"
    up.effective_chat = chat

    msg = MagicMock(spec=Message)
    msg.text = text
    msg.chat_id = chat.id
    msg.from_user = user
    msg.reply_text = AsyncMock()
    msg.reply_document = AsyncMock()
    up.message = msg
    return up


def test_help_view_and_help_owner():
    print("--- 1. Testing /help & /help_owner ---")
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")
    admin_user = make_mock_user(2001, "admin1", "Admin")
    student_user = make_mock_user(3001, "student1", "Student")

    ctx = MagicMock()
    mock_db = MagicMock()
    mock_conn = MagicMock()
    ctx.application.bot_data = {"conn": mock_conn, "db": mock_db}

    # Mock user_row in commands.py
    async def mock_user_row(conn, db, uid):
        if uid == OWNER_ID:
            return {"telegram_id": OWNER_ID, "role": ROLE_OWNER, "profile_json": "{}"}
        elif uid == 2001:
            return {"telegram_id": 2001, "role": ROLE_ADMIN, "profile_json": "{}"}
        else:
            return {"telegram_id": 3001, "role": ROLE_STUDENT, "profile_json": "{}"}

    with unittest_mock_patch("bot.handlers.commands.user_row", side_effect=mock_user_row):
        # A. Admin /help
        up_admin = make_mock_update(admin_user, "/help")
        run_sync(commands.cmd_help(up_admin, ctx))
        admin_text = up_admin.message.reply_text.call_args[0][0]
        assert "<b>Admin</b>" in admin_text
        assert "<b>Owner</b>" not in admin_text
        assert "/help_owner" not in admin_text
        print("  [PASS] Admin sees clean Admin help without Owner clutter")

        # B. Owner /help
        up_owner = make_mock_update(owner_user, "/help")
        run_sync(commands.cmd_help(up_owner, ctx))
        owner_text = up_owner.message.reply_text.call_args[0][0]
        assert "<b>Admin</b>" in owner_text
        assert "<b>Owner</b>" not in owner_text, "Owner block must not clutter normal /help"
        assert "/help_owner" in owner_text, "Owner must see hint to /help_owner"
        print("  [PASS] Owner /help matches Admin view + includes /help_owner hint")

        # C. Non-owner /help_owner -> Blocked
        up_student_ownerhelp = make_mock_update(student_user, "/help_owner")
        run_sync(commands.cmd_help_owner(up_student_ownerhelp, ctx))
        blocked_text = up_student_ownerhelp.message.reply_text.call_args[0][0]
        assert "hanya dapat diakses oleh Founder / Owner" in blocked_text
        print("  [PASS] Non-owner blocked from /help_owner")

        # D. Owner /help_owner -> Full Owner Encyclopedia
        up_ownerhelp = make_mock_update(owner_user, "/help_owner")
        run_sync(commands.cmd_help_owner(up_ownerhelp, ctx))
        full_owner_text = up_ownerhelp.message.reply_text.call_args[0][0]
        assert "Panduan Lengkap Perintah Khusus Owner / Founder" in full_owner_text
        assert "/setrole purna all" in full_owner_text
        assert "/generasi_tutup" in full_owner_text
        assert "/generasi_atur" in full_owner_text
        assert "/generasi" in full_owner_text
        assert "/pindah_data" in full_owner_text
        assert "/gencode" in full_owner_text
        assert "/owner_reset" in full_owner_text
        print("  [PASS] Owner receives complete /help_owner guide")


from unittest.mock import patch as unittest_mock_patch


def test_export_zip_includes_json():
    print("\n--- 2. Testing /export_kelulusan ZIP Includes JSON File ---")
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        output_dir = temp_dir / "output_test"
        zip_path = temp_dir / "test_kelulusan.zip"

        sample_student = StudentGraduationData(
            nama="Aluna Valencia",
            nim="02004010093",
            ttl="11 Mei 2010",
            jurusan="Fotografi",
            fakultas="Ilmu Budaya",
            courses=[CourseGrade(kode="KU101", nama="Kaidah Kebahasaan", sks=2, nilai="A-", ip="3,70")],
            ipk="3,94",
            predikat="CUMLAUDE",
            clubs=[ClubGrade(nama="Klub Memasak", sks=2, nilai="A", ip="4,00")],
            ikk="4,00",
            is_lulus=True,
            generasi="1",
        )

        success_count, created_files = graduation._sync_export_documents(
            graduates=[sample_student],
            output_dir=output_dir,
            photos_map=None,
            gen_val="1",
        )

        assert success_count == 1
        # Check that JSON file was created in output_dir
        json_file = output_dir / "graduation_records_gen1.json"
        assert json_file.exists(), "graduation_records_gen1.json must exist in output_dir"
        assert json_file in created_files, "json file must be tracked in created_files"

        # Verify JSON content
        with open(json_file, "r", encoding="utf-8") as jf:
            data = json.load(jf)
            assert "02004010093" in data
            assert data["02004010093"]["nama"] == "Aluna Valencia"
        print("  [PASS] graduation_records_gen1.json generated and validated in output folder")

        # Create zip like cmd_export_kelulusan does
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in created_files:
                zf.write(file_path, arcname=file_path.name)

        # Inspect zip contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "graduation_records_gen1.json" in namelist, "JSON file must be packaged inside the zip file!"
            assert any(f.endswith("_Transkrip.png") for f in namelist)
            assert any(f.endswith("_Ijazah.png") for f in namelist)
            print(f"  [PASS] ZIP contains {len(namelist)} files, including {namelist[0]}!")


def test_export_kelulusan_restricted_to_owner():
    print("\n--- 3. Testing /export_kelulusan Restricted to Owner Only ---")
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")
    admin_user = make_mock_user(2001, "admin1", "Admin")

    ctx = MagicMock()
    mock_db = MagicMock()
    mock_conn = MagicMock()
    ctx.application.bot_data = {"conn": mock_conn, "db": mock_db}

    async def mock_user_row(conn, db, uid):
        if uid == OWNER_ID:
            return {"telegram_id": OWNER_ID, "role": ROLE_OWNER, "profile_json": "{}"}
        elif uid == 2001:
            return {"telegram_id": 2001, "role": ROLE_ADMIN, "profile_json": "{}"}
        return None

    with unittest_mock_patch("bot.handlers.graduation.user_row", side_effect=mock_user_row), \
         unittest_mock_patch("bot.handlers.commands.user_row", side_effect=mock_user_row):
        # Admin runs /export_kelulusan -> REJECTED
        up_admin = make_mock_update(admin_user, "/export_kelulusan")
        run_sync(graduation.cmd_export_kelulusan(up_admin, ctx))
        admin_reply = up_admin.message.reply_text.call_args[0][0]
        assert "hanya dapat dijalankan oleh Founder / Owner" in admin_reply
        print("  [PASS] Admin blocked from running /export_kelulusan")

        # Admin runs /export_photos -> REJECTED
        up_admin_photos = make_mock_update(admin_user, "/export_photos")
        run_sync(commands.cmd_export_photos(up_admin_photos, ctx))
        admin_photos_reply = up_admin_photos.message.reply_text.call_args[0][0]
        assert "hanya dapat dijalankan oleh Founder / Owner" in admin_photos_reply
        print("  [PASS] Admin blocked from running /export_photos")

        # Admin runs /ospek_mode -> REJECTED
        up_admin_ospek = make_mock_update(admin_user, "/ospek_mode on")
        run_sync(commands.cmd_ospek_mode(up_admin_ospek, ctx))
        admin_ospek_reply = up_admin_ospek.message.reply_text.call_args[0][0]
        assert "hanya dapat dijalankan oleh Founder / Owner" in admin_ospek_reply
        print("  [PASS] Admin blocked from running /ospek_mode")

        # Owner runs /export_kelulusan -> ALLOWED (proceeds past auth gate)
        up_owner = make_mock_update(owner_user, "/export_kelulusan")
        # mock graduates to empty to exit cleanly
        with unittest_mock_patch("bot.handlers.graduation.get_all_graduates", return_value=[]):
            run_sync(graduation.cmd_export_kelulusan(up_owner, ctx))
            owner_reply = up_owner.message.reply_text.call_args[0][0]
            assert "Tidak ada data lulusan" in owner_reply
            print("  [PASS] Owner allowed to run /export_kelulusan")


def test_cmd_push_and_cmd_pull():
    print("--- 4. Testing /pull & /push commands ---")
    owner_user = make_mock_user(OWNER_ID, "founder", "Owner")
    student_user = make_mock_user(3001, "student1", "Student")

    ctx = MagicMock()
    mock_db = MagicMock()
    mock_conn = MagicMock()
    ctx.application.bot_data = {"conn": mock_conn, "db": mock_db}

    async def mock_user_row(conn, db, uid):
        if uid == OWNER_ID:
            return {"telegram_id": OWNER_ID, "role": ROLE_OWNER, "profile_json": "{}"}
        return {"telegram_id": 3001, "role": ROLE_STUDENT, "profile_json": "{}"}

    with unittest_mock_patch("bot.handlers.commands.user_row", side_effect=mock_user_row):
        # 1. Non-owner /pull -> Rejected
        up_student_pull = make_mock_update(student_user, "/pull")
        run_sync(commands.cmd_pull(up_student_pull, ctx))
        assert "Tidak diizinkan. Hanya owner" in up_student_pull.message.reply_text.call_args[0][0]

        # 2. Non-owner /push -> Rejected
        up_student_push = make_mock_update(student_user, "/push")
        run_sync(commands.cmd_push(up_student_push, ctx))
        assert "Tidak diizinkan. Hanya owner" in up_student_push.message.reply_text.call_args[0][0]

        # 3. Owner /pull -> Calls git pull
        up_owner_pull = make_mock_update(owner_user, "/pull")
        mock_pull_msg = MagicMock()
        mock_pull_msg.edit_text = AsyncMock()
        up_owner_pull.message.reply_text = AsyncMock(return_value=mock_pull_msg)

        mock_res_pull = MagicMock(stdout="Already up to date.\n")
        with unittest_mock_patch("subprocess.run", return_value=mock_res_pull):
            run_sync(commands.cmd_pull(up_owner_pull, ctx))
            assert "Already up to date." in mock_pull_msg.edit_text.call_args[0][0]

        # 4. Owner /push (clean repo) -> Calls git status & git push
        up_owner_push = make_mock_update(owner_user, "/push")
        mock_push_msg = MagicMock()
        mock_push_msg.edit_text = AsyncMock()
        up_owner_push.message.reply_text = AsyncMock(return_value=mock_push_msg)

        def mock_subp_run(cmd, **kwargs):
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(stdout="")
            elif "push" in cmd:
                return MagicMock(stdout="Everything up-to-date\n", stderr="")
            return MagicMock(stdout="", stderr="")

        with unittest_mock_patch("subprocess.run", side_effect=mock_subp_run):
            run_sync(commands.cmd_push(up_owner_push, ctx))
            assert "Git Push Berhasil" in mock_push_msg.edit_text.call_args[0][0]
            assert "Everything up-to-date" in mock_push_msg.edit_text.call_args[0][0]

        # 5. Owner /push with dirty repo & custom message -> adds, commits, pushes
        up_owner_push_dirty = make_mock_update(owner_user, "/push sync kelulusan")
        mock_push_msg_dirty = MagicMock()
        mock_push_msg_dirty.edit_text = AsyncMock()
        up_owner_push_dirty.message.reply_text = AsyncMock(return_value=mock_push_msg_dirty)

        executed_cmds = []
        def mock_subp_run_dirty(cmd, **kwargs):
            executed_cmds.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(stdout=" M data/graduation_records.json\n")
            elif "commit" in cmd:
                return MagicMock(stdout="[main abc1234] sync kelulusan\n")
            elif "push" in cmd:
                return MagicMock(stdout="To github.com:user/repo.git\n   abc1234..def5678  main -> main\n", stderr="")
            return MagicMock(stdout="", stderr="")

        with unittest_mock_patch("subprocess.run", side_effect=mock_subp_run_dirty):
            run_sync(commands.cmd_push(up_owner_push_dirty, ctx))
            assert any(cmd == ["git", "status", "--porcelain"] for cmd in executed_cmds)
            assert any(cmd == ["git", "add", "-A"] for cmd in executed_cmds)
            assert any("commit" in cmd and "sync kelulusan" in cmd for cmd in executed_cmds)
            assert any("push" in cmd for cmd in executed_cmds)
            assert "Git Push Berhasil" in mock_push_msg_dirty.edit_text.call_args[0][0]


def main():
    print("==================================================================")
    print("STARTING TEST SUITE: /help, /help_owner & ZIP JSON INCLUSION")
    print("==================================================================")
    test_help_view_and_help_owner()
    test_export_zip_includes_json()
    test_export_kelulusan_restricted_to_owner()
    test_cmd_push_and_cmd_pull()
    print("\n==================================================================")
    print("ALL TESTS PASSED! (4/4 Suites)")
    print("==================================================================")


if __name__ == "__main__":
    main()
