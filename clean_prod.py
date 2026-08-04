import asyncio
import os
from dotenv import load_dotenv
from bot.database import Database

async def clean():
    load_dotenv(".env")
    db = Database()
    conn = await db.connect()
    try:
        for user_id in [1, 2, 3]:
            await conn.execute("DELETE FROM agra_ledger WHERE target_telegram_id = ? OR actor_id = ?", (user_id, user_id))
            await conn.execute("DELETE FROM task_submissions WHERE student_id = ? OR reviewed_by = ?", (user_id, user_id))
            await conn.execute("DELETE FROM task_assignments WHERE created_by = ?", (user_id,))
            await conn.execute("DELETE FROM attendance_records WHERE telegram_id = ?", (user_id,))
            await conn.execute("DELETE FROM attendance_sessions WHERE opened_by = ?", (user_id,))
            await conn.execute("DELETE FROM menfess_history WHERE sender_id = ? OR receiver_id = ?", (user_id, user_id))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        await conn.commit()
        print("Production DB cleaned from dummy IDs!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(clean())
