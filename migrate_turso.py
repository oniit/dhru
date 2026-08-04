import asyncio
import os
import libsql_client
from dotenv import load_dotenv

async def main():
    load_dotenv(".env")
    url = os.environ.get("TURSO_DB_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("URL atau Token Turso tidak ditemukan di .env")
        return
        
    client = libsql_client.create_client(url=url, auth_token=token)
    
    print("Mengeksekusi CREATE TABLE menfess_history di Turso...")
    
    sql = """
    CREATE TABLE IF NOT EXISTS menfess_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        gift_agra INTEGER DEFAULT 0,
        created_at REAL NOT NULL,
        FOREIGN KEY (sender_id) REFERENCES users(telegram_id),
        FOREIGN KEY (receiver_id) REFERENCES users(telegram_id)
    );
    """
    
    try:
        await client.execute(sql)
        print("✅ Tabel menfess_history berhasil dibuat di Turso!")
    except Exception as e:
        print(f"❌ Gagal membuat tabel: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
