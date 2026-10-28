import pytest
from bot.database import Database, ROLE_STUDENT, ROLE_PURVA
from bot.handlers.common import profile_from_row

@pytest.mark.asyncio
async def test_purva_sks_banking_and_fields():
    db = Database()
    conn = await db.connect()
    test_uid = 9988775544

    try:
        # Create user
        await db.upsert_user_from_telegram(
            conn,
            telegram_id=test_uid,
            username="student_tester",
            first_name="Stud",
            last_name="Ent",
            language_code="id",
            is_premium=False,
            is_bot=False,
            raw_profile={},
        )

        # 1. User becomes a Student with some SKS
        await db.set_role(conn, test_uid, ROLE_STUDENT)
        await db.set_profile_partial(conn, test_uid, {
            "faculty": "fmipa",
            "major": "ik", # 2 credits maybe? wait, classes give credits.
            "class_enrolled": ["umum_kk", "umum_pd"], # 2 + 2 = 4 SKS
            "club_enrolled": ["ui"], # 2 SKS
            "muse": "MuseA",
            "birth_date": "2000-01-01",
        })
        
        row = await db.get_user(conn, test_uid)
        prof = profile_from_row(row)
        assert prof["faculty"] == "fmipa"
        assert prof["major"] == "ik"
        assert prof["muse"] == "MuseA"
        # 12 SKS (6 from major classes + 4 from general classes + 2 from club)
        assert prof.get("total_sks") == 12
        assert prof.get("student_id") is not None # Generated dynamically

        # 2. User graduates and becomes PURVA
        await db.set_role(conn, test_uid, ROLE_PURVA)
        row_purva = await db.get_user(conn, test_uid)
        prof_purva = profile_from_row(row_purva)

        # Assert specific fields are removed/hidden like public
        assert prof_purva.get("major") is None
        assert prof_purva.get("student_id") is None
        
        # Assert preserved fields
        assert prof_purva.get("muse") == "MuseA"
        assert prof_purva.get("birth_date") == "2000-01-01"

        # Assert SKS is preserved securely!
        assert prof_purva.get("accumulated_sks") == 12
        assert prof_purva.get("total_sks") == 12

        # 3. User re-enrolls as STUDENT
        await db.set_role(conn, test_uid, ROLE_STUDENT)
        await db.set_profile_partial(conn, test_uid, {
            "faculty": "fib",
            "major": "sm",
            "class_enrolled": ["umum_kk"], # 2 SKS
            "club_enrolled": ["um"], # 2 SKS
        })
        
        row_student = await db.get_user(conn, test_uid)
        prof_student = profile_from_row(row_student)
        
        # SKS should be accumulated (12 from before + 12 new = 24)
        assert prof_student.get("accumulated_sks") == 12
        assert prof_student.get("total_sks") == 24
        assert prof_student.get("student_id") is not None
        assert prof_student.get("muse") == "MuseA" # Preserved!

        # 4. User graduates again
        await db.set_role(conn, test_uid, ROLE_PURVA)
        row_final = await db.get_user(conn, test_uid)
        prof_final = profile_from_row(row_final)
        
        assert prof_final.get("accumulated_sks") == 24
        assert prof_final.get("total_sks") == 24
        assert prof_final.get("student_id") is None

    finally:
        try:
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_uid,))
            await conn.commit()
        finally:
            await conn.close()
