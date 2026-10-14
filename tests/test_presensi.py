import asyncio
import os
import json
import pytest

from bot.database import Database

@pytest.mark.asyncio
async def test_presensi_logic():
    db = Database()
    conn = await db.connect()
    
    print(f"Connected to DB: {db.path} (Turso)")

    try:
        # 1. Shishya Seni Musik (major: sm)
        await db.upsert_user_from_telegram(conn, telegram_id=9003, username="shishya_musik", first_name="Anak", last_name="Musik", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.set_role(conn, 9003, "student")
        await db.set_profile_partial(conn, 9003, {"major": "sm", "full_name": "Anak Musik"})
        
        # 3. Owner (buat buka sesi)
        await db.upsert_user_from_telegram(conn, telegram_id=9000, username="owner_test", first_name="O1", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.set_role(conn, 9000, "owner")
        
        # Buka sesi Sejarah Musik (khusus sm)
        sid_musik = await db.open_attendance_session(conn, class_id="sm", title="Sejarah Musik", opened_by=9000, chat_id=-100)
        
        # Buka sesi Dasar Fotografi (khusus sf)
        sid_foto = await db.open_attendance_session(conn, class_id="df", title="Dasar Fotografi", opened_by=9000, chat_id=-100)
        
        from bot.handlers.attendance import _record_hadir, classes_for_presensi
        from bot.handlers.common import get_user_jabatans
        
        async def simulate_hadir(uid, sid):
            row = await db.get_user(conn, uid)
            profile = json.loads(row["profile_json"])
            user_classes = classes_for_presensi(profile)
            jabs = get_user_jabatans(profile)
            if row["role"] in ("internal", "admin", "owner") or "d_sekre" in jabs:
                user_classes.append("staff_manual")
            if row["role"] in ("bem", "admin", "owner"):
                user_classes.append("bem_manual")
            if row["role"] != "public":
                user_classes.append("event_bebas")
            return await _record_hadir(db, conn, sid, uid, row["role"], user_classes)
            
        print("\nTest 1: Shishya Musik -> absen kelas Sejarah Musik (Khusus Anak Musik)")
        print("Expected: BERHASIL")
        ok, msg, _ = await simulate_hadir(9003, sid_musik)
        print(f"Result: {ok} | Msg: {msg}\n")
        
        print("Test 2: Shishya Musik -> absen kelas Dasar Fotografi (Khusus Anak Fotografi)")
        print("Expected: GAGAL (Di luar akses presensi)")
        ok, msg, _ = await simulate_hadir(9003, sid_foto)
        print(f"Result: {ok} | Msg: {msg}\n")

        # Cleanup
        await db.close_attendance_session(conn, sid_musik)
        await db.close_attendance_session(conn, sid_foto)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_presensi_logic())
