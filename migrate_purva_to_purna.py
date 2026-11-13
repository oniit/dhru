"""
One-time migration: rename role 'purva' -> 'purna' in Turso DB.
Run once, then delete this file.
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from bot.database import Database

async def main():
    db = Database()
    conn = await db.connect()
    try:
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE role = 'purva'")
        row = await cur.fetchone()
        count = row[0] if row else 0
        print(f"Found {count} user(s) with role 'purva'")
        
        if count > 0:
            await conn.execute("UPDATE users SET role = 'purna' WHERE role = 'purva'")
            await conn.commit()
            print(f"✅ Migrated {count} user(s) from role 'purva' to 'purna'")
        else:
            print("ℹ️ No users with role 'purva' found. Nothing to migrate.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
