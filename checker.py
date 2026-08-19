import asyncio
import logging
import re
from decouple import config
from pyrogram import Client, errors

from bot.database import Database
import os

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("checker")

API_ID = config("API_ID", cast=int, default=0)
API_HASH = config("API_HASH", default="")
BOT_TOKEN = config("BOT_TOKEN", default="")

if not API_ID or not API_HASH:
    raise ValueError("API_ID atau API_HASH tidak ditemukan di .env")

# Initialize Pyrogram Client
app = Client("checker", api_id=API_ID, api_hash=API_HASH)

async def process_pending_links():
    db = Database()
    conn = await db.connect()
    
    while True:
        try:
            # Get pending verifications
            cur = await conn.execute("SELECT * FROM promo_verifications WHERE status = 'PENDING'")
            pending_rows = await cur.fetchall()
            
            for row in pending_rows:
                req_id = row["id"]
                main_user_id = row["user_id"]
                link = row["link"]
                created_at = row["created_at"]
                
                # Check expiration (2 days)
                import time
                if time.time() - created_at > 2 * 24 * 3600:
                    await conn.execute("UPDATE promo_verifications SET status = 'EXPIRED' WHERE id = ?", (req_id,))
                    await conn.commit()
                    continue

                log.info(f"Checking link {link} for user {main_user_id}...")
                
                # Parse link: https://t.me/username/123 or https://t.me/c/12345/123
                # We will handle standard public links: t.me/groupname/msgid
                match = re.search(r"t\.me/([^/]+)/(\d+)", link)
                if not match:
                    await conn.execute("UPDATE promo_verifications SET status = 'INVALID_URL' WHERE id = ?", (req_id,))
                    await conn.commit()
                    continue
                    
                chat_id = match.group(1)
                msg_id = int(match.group(2))
                
                if chat_id == "c":
                    # Private group format: t.me/c/chat_id/msg_id
                    # Pyrogram needs -100 prefix for chat IDs
                    # We might skip private for now or handle them if bot is in them
                    await conn.execute("UPDATE promo_verifications SET status = 'PRIVATE_GROUP_NOT_SUPPORTED' WHERE id = ?", (req_id,))
                    await conn.commit()
                    continue

                try:
                    msg = await app.get_messages(chat_id, msg_id)
                    if not msg or msg.empty:
                        await conn.execute("UPDATE promo_verifications SET status = 'NOT_FOUND' WHERE id = ?", (req_id,))
                        await conn.commit()
                        continue
                        
                    text = msg.text or msg.caption or ""
                    sender_id = msg.from_user.id if msg.from_user else None
                    
                    # 1. Cek kata kunci
                    if "lchs" not in text.lower():
                        await conn.execute("UPDATE promo_verifications SET status = 'NO_KEYWORD' WHERE id = ?", (req_id,))
                        await conn.commit()
                        continue
                        
                    # 2. Cek kepemilikan pengirim
                    valid_sender = False
                    if sender_id == main_user_id:
                        valid_sender = True
                    else:
                        # Cek linked accounts
                        linked_accounts = await db.get_linked_accounts(conn, main_user_id)
                        if sender_id in linked_accounts:
                            valid_sender = True
                            
                    if not valid_sender:
                        await conn.execute("UPDATE promo_verifications SET status = 'SENDER_MISMATCH' WHERE id = ?", (req_id,))
                        await conn.commit()
                        continue
                        
                    # 3. Lolos semua validasi!
                    await conn.execute("UPDATE promo_verifications SET status = 'VALID' WHERE id = ?", (req_id,))
                    await db.add_agra(
                        conn,
                        target_id=main_user_id,
                        actor_id=main_user_id,
                        amount=1,
                        description="Reward promosi LPM",
                        chat_id=None,
                        message_id=None
                    )
                    await conn.commit()
                    log.info(f"Link {link} VALID. +1 Agra for {main_user_id}")
                    
                    # Optional: Kirim notif via bot API biasa
                    # But since this is a separate script, we can use requests or aiogram to send a message to user
                    import requests
                    requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": main_user_id,
                            "text": f"✅ Link LPM kamu berhasil divalidasi!\n{link}\nKamu mendapatkan +1 Agra."
                        }
                    )
                    
                except errors.FloodWait as e:
                    log.warning(f"FloodWait: sleeping for {e.value} seconds")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    log.error(f"Error reading message {link}: {e}")
                    await conn.execute("UPDATE promo_verifications SET status = 'ERROR' WHERE id = ?", (req_id,))
                    await conn.commit()

        except Exception as e:
            log.error(f"Database error in checker loop: {e}")
            
        # Polling delay
        await asyncio.sleep(5)

async def main():
    log.info("Starting Pyrogram Checker...")
    await app.start()
    log.info("Pyrogram logged in successfully. Starting polling loop...")
    try:
        await process_pending_links()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.stop()

if __name__ == "__main__":
    app.run(main())
