import asyncio
import os
os.environ["TURSO_DB_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
import time
from bot.database import Database

async def run_tests():
    print("=== Memulai Tes Logika & Fungsi Inti ===")
    os.environ["TURSO_DATABASE_URL"] = "file:test_logic_88.sqlite3"
    
    for ext in ["", "-wal", "-shm"]:
        f = "test_logic_88.sqlite3" + ext
        if os.path.exists(f):
            try: os.remove(f)
            except: pass
        
    from pathlib import Path
    db = Database(path=Path("test_logic_88.sqlite3"))
    conn = await db.connect()
    print(f"DEBUG: db.path is {db.path}")
    
    try:
        # 1. User Creation
        print("1. Testing Registrasi User...")
        await db.upsert_user_from_telegram(conn, telegram_id=1, username="owner_user", first_name="Owner", last_name="", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.set_role(conn, 1, "owner")
        
        await db.upsert_user_from_telegram(conn, telegram_id=2, username="normal_user1", first_name="User", last_name="1", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        await db.upsert_user_from_telegram(conn, telegram_id=3, username="normal_user2", first_name="User", last_name="2", language_code="id", is_premium=False, is_bot=False, raw_profile={})
        print("   -> OK (Berhasil registrasi multi-role)")
        
        # 2. Testing Agra Economics (termasuk fix TOCTOU)
        print("2. Testing Validasi Ekonomi Agra (Anti-Minus/TOCTOU)...")
        await db.add_agra(conn, target_id=2, actor_id=1, amount=100, description="Bonus awal", chat_id=None, message_id=None)
        total = await db.agra_total(conn, 2)
        print(f"DEBUG: total agra is {total}")
        assert total == 100, f"Expected 100, got {total}"
        
        # Test deduction success
        success = await db.deduct_agra_if_sufficient(conn, target_id=2, actor_id=2, amount=50, description="Beli barang", chat_id=None, message_id=None)
        assert success is True
        total = await db.agra_total(conn, 2)
        assert total == 50
        
        # Test deduction failure (anti-minus)
        success = await db.deduct_agra_if_sufficient(conn, target_id=2, actor_id=2, amount=100, description="Beli barang mahal", chat_id=None, message_id=None)
        assert success is False
        total = await db.agra_total(conn, 2)
        assert total == 50 # Saldo tidak boleh berubah
        print("   -> OK (Saldo aman, tidak tembus minus)")
        
        # 3. Testing Menfess
        print("3. Testing Modul Menfess...")
        await db.add_menfess(conn, sender_id=2, receiver_id=3, message_text="Pesan rahasia", gift_agra=10)
        inbox = await db.get_menfess_inbox(conn, telegram_id=3)
        assert len(inbox) == 1
        assert inbox[0]["message_text"] == "Pesan rahasia"
        print("   -> OK (Data masuk dan terbaca oleh target)")
        
        # 4. Testing Absensi (Attendance)
        print("4. Testing Presensi (Atomic Constraints)...")
        sess_id = await db.open_attendance_session(conn, class_id="kelas1", title="Pertemuan 1", opened_by=1, chat_id=-100)
        success, msg = await db.record_attendance(conn, session_id=sess_id, telegram_id=2)
        assert success is True, f"Msg: {msg}"
        
        # Absen ulang (harus gagal/already recorded)
        success2, msg2 = await db.record_attendance(conn, session_id=sess_id, telegram_id=2)
        assert success2 is False
        
        # Tutup sesi
        await db.close_attendance_session(conn, sess_id)
        sess_data = await db.get_attendance_session(conn, sess_id)
        assert sess_data["closed_at"] is not None
        print("   -> OK (Sistem menolak absen ganda, penutupan sesi berhasil disimpan)")
        
        # 5. Testing Tugas (Tasks)
        print("5. Testing Manajemen Tugas & Review (Validasi Saldo)...")
        task_id = await db.create_task(conn, class_id="kelas1", title="Tugas 1", created_by=1)
        
        # Submit tugas
        submission_id = await db.submit_task(conn, task_id=task_id, student_id=2, content="Ini tugas saya")
        
        # Review tugas (atomic update, mencegah poin ganda)
        success_review = await db.review_submission(conn, submission_id=submission_id, accept=True, reviewed_by=1)
        assert success_review is True
        
        # Coba review dua kali (simulasi spam concurrent)
        # Skenario spam review seharusnya ditolak (0 row di-update karena sudah status 'reviewed'/'accepted')
        success_review2 = await db.review_submission(conn, submission_id=submission_id, accept=True, reviewed_by=1)
        assert success_review2 is False
        print("   -> OK (Review mengalirkan status dengan akurat, dan menolak double-review)")
        
        print("\n=== SEMUA FUNGSI INTI (LOGIC) BERJALAN SEMPURNA! ===")
        
    except AssertionError as e:
        print(f"\n[X] FAILED: {e}")
    except Exception as e:
        print(f"\n[X] ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await conn.close()
        # Biarkan file db agar bisa diinspeksi

if __name__ == "__main__":
    asyncio.run(run_tests())
