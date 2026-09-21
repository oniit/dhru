import asyncio
from bot.database import Database
import sqlite3

async def fix():
    db = Database()
    conn = await db.get_connection()
    try:
        cur = await conn.execute("SELECT telegram_id, role, profile_json FROM users")
        rows = await cur.fetchall()
        for row in rows:
            uid = row["telegram_id"]
            role = row["role"]
            import json
            prof = json.loads(row["profile_json"] or "{}")
            # This will re-run the _apply_generated_profile_fields internally
            await db.set_profile_partial(conn, uid, prof)
        await conn.commit()
        print(f"Berhasil memperbarui {len(rows)} profil.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix())
