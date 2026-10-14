import pytest
from bot.database import Database

@pytest.mark.asyncio
async def test_presensi_ukm():
    db = Database()
    conn = await db.connect()
    
    print(f"Connected to DB: {db.path} (Turso)")

    try:
        # 1. Shishya ikut Klub Memasak (um) dan Klub Bhs Inggris (ui)
        await db.upsert_user_from_telegram(conn, telegram_id=9005, username="shishya_ukm", first_name="Anak", last_name="UKM", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.set_role(conn, 9005, "student")
        await db.set_profile_partial(conn, 9005, {"major": "if", "club_enrolled": ["um", "ui"], "full_name": "Anak UKM"})
        
        # 2. Owner (buat buka sesi)
        await db.upsert_user_from_telegram(conn, telegram_id=9000, username="owner_test", first_name="O1", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.set_role(conn, 9000, "owner")
        
        # Buka sesi Klub Memasak (um)
        sid_um = await db.open_attendance_session(conn, class_id="um", title="Klub Memasak", opened_by=9000, chat_id=-100)
        
        # Buka sesi Klub Kewirausahaan (uk)
        sid_uk = await db.open_attendance_session(conn, class_id="uk", title="Klub Kewirausahaan", opened_by=9000, chat_id=-100)
        
        from bot.handlers.attendance import _record_hadir, classes_for_presensi
        
        async def simulate_hadir(uid, sid):
            row = await db.get_user(conn, uid)
            profile = json.loads(row["profile_json"])
            user_classes = classes_for_presensi(profile)
            if row["role"] in ("internal", "admin", "owner"):
                user_classes.append("staff_manual")
            if row["role"] in ("bem", "admin", "owner"):
                user_classes.append("bem_manual")
            if row["role"] != "public":
                user_classes.append("event_bebas")
            return await _record_hadir(db, conn, sid, uid, row["role"], user_classes)
            
        print("\nTest 1: Shishya (Klub Memasak) -> absen sesi Klub Memasak (um)")
        print("Expected: BERHASIL")
        ok, msg, _ = await simulate_hadir(9005, sid_um)
        print(f"Result: {ok} | Msg: {msg}\n")
        
        print("Test 2: Shishya (Klub Memasak) -> absen sesi Klub Kewirausahaan (uk)")
        print("Expected: GAGAL (Di luar akses)")
        ok, msg, _ = await simulate_hadir(9005, sid_uk)
        print(f"Result: {ok} | Msg: {msg}\n")

        # Cleanup
        await db.close_attendance_session(conn, sid_um)
        await db.close_attendance_session(conn, sid_uk)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_presensi_ukm())
