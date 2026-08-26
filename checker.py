import asyncio
import logging
import re
import os
from dotenv import load_dotenv
from pyrogram import Client, errors

from bot.database import Database

# Load environment variables
load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("checker")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not API_ID or not API_HASH:
    raise ValueError("API_ID atau API_HASH tidak ditemukan di .env")

# Initialize Pyrogram Client
app = Client("checker", api_id=API_ID, api_hash=API_HASH)

async def process_userbot_requests(conn):
    try:
        cur = await conn.execute("SELECT * FROM userbot_requests WHERE status = 'PENDING'")
        pending_rows = await cur.fetchall()
        for row in pending_rows:
            req_id = row["id"]
            chat_id = row["chat_id"]
            action = row["action"]
            
            # Check expiration (if older than 30 seconds, mark as expired)
            import time
            if time.time() - row["created_at"] > 30:
                await conn.execute("UPDATE userbot_requests SET status = 'ERROR', result = 'EXPIRED' WHERE id = ?", (req_id,))
                await conn.commit()
                continue
                
            if action == "GET_MEMBERS":
                log.info(f"Fetching members for chat {chat_id}")
                try:
                    members = []
                    async for member in app.get_chat_members(int(chat_id)):
                        if member.user and not member.user.is_bot and not member.user.is_deleted:
                            members.append(member.user.id)
                    import json
                    result_json = json.dumps(members)
                    await conn.execute("UPDATE userbot_requests SET status = 'DONE', result = ? WHERE id = ?", (result_json, req_id))
                    await conn.commit()
                    log.info(f"Fetched {len(members)} members for chat {chat_id}")
                except Exception as e:
                    log.error(f"Error fetching members for chat {chat_id}: {e}")
                    await conn.execute("UPDATE userbot_requests SET status = 'ERROR', result = ? WHERE id = ?", (str(e), req_id))
                    await conn.commit()
    except Exception as e:
        log.error(f"Error in process_userbot_requests: {e}")

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
                promo_type = row.get("promo_type", "lpm")
                created_at = row["created_at"]
                
                # Check expiration (2 days)
                import time
                if time.time() - created_at > 2 * 24 * 3600:
                    await conn.execute("UPDATE promo_verifications SET status = 'EXPIRED' WHERE id = ?", (req_id,))
                    await conn.commit()
                    continue

                log.info(f"Checking {promo_type} link {link} for user {main_user_id}...")
                
                lpm_keyword = await db.get_setting(conn, "promo_lpm_keyword", "dhruva")
                story_post_link = await db.get_setting(conn, "promo_story_post", "")

                if promo_type == "story":
                    match = re.search(r"t\.me/([^/]+)/s/(\d+)", link)
                    if not match:
                        await conn.execute("UPDATE promo_verifications SET status = 'INVALID_URL' WHERE id = ?", (req_id,))
                        await conn.commit()
                        import requests
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": main_user_id,
                                "text": f"❌ Gagal memvalidasi link {link}\n\nFormat link Story tidak dikenali. (Pastikan format: t.me/username/s/123)"
                            }
                        )
                        continue
                        
                    username = match.group(1)
                    story_id = int(match.group(2))
                    
                    try:
                        stories = await app.get_stories(username, [story_id])
                        if not stories or not stories[0]:
                            await conn.execute("UPDATE promo_verifications SET status = 'NOT_FOUND' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nStory tidak ditemukan atau akun di-private."
                                }
                            )
                            continue
                            
                        story = stories[0]
                        sender_id = story.from_user.id if story.from_user else None
                        
                        valid_sender = False
                        if sender_id == main_user_id:
                            valid_sender = True
                        else:
                            linked_accounts = await db.get_linked_accounts(conn, main_user_id)
                            if sender_id in linked_accounts:
                                valid_sender = True
                                
                        if not valid_sender:
                            await conn.execute("UPDATE promo_verifications SET status = 'SENDER_MISMATCH' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nPengirim Story bukan akun utamamu dan bukan dari Akun Kerja yang tertaut."
                                }
                            )
                            continue

                        # Check MediaAreaChannelPost
                        target_match = re.search(r"t\.me/([^/]+)/(\d+)", story_post_link)
                        has_channel_post = False
                        
                        if target_match:
                            target_channel = target_match.group(1)
                            target_msg_id = int(target_match.group(2))
                            
                            try:
                                target_chat = await app.get_chat(target_channel)
                                target_channel_id = target_chat.id
                            except:
                                target_channel_id = None

                            if story.media_areas:
                                for area in story.media_areas:
                                    # MediaAreaChannelPost has chat and message_id in pyrofork
                                    area_chat = getattr(area, "chat", None)
                                    area_channel_id = area_chat.id if area_chat else getattr(area, "channel_id", None)
                                    area_msg_id = getattr(area, "message_id", None)
                                    
                                    # Sometimes API returns channel_id as raw ID without -100 prefix, so we check carefully
                                    if area_channel_id and area_msg_id:
                                        if str(area_channel_id).replace("-100", "") == str(target_channel_id).replace("-100", "") and area_msg_id == target_msg_id:
                                            has_channel_post = True
                                            break
                                            
                        if not has_channel_post:
                            await conn.execute("UPDATE promo_verifications SET status = 'NO_KEYWORD' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            reason = f"(Harus memuat repost dari: {story_post_link})" if story_post_link else "(Link target belum disetel oleh admin)"
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nStory kamu tidak memuat (repost) postingan yang sesuai. {reason}"
                                }
                            )
                            continue
                            
                        # VALID STORY
                        await conn.execute("UPDATE promo_verifications SET status = 'VALID' WHERE id = ?", (req_id,))
                        await db.add_agra(
                            conn,
                            target_id=main_user_id,
                            actor_id=main_user_id,
                            amount=3,
                            description="Reward promosi Story",
                            chat_id=None,
                            message_id=None
                        )
                        await conn.commit()
                        import requests
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": main_user_id,
                                "text": f"✅ Link Story kamu berhasil divalidasi!\n{link}\nKamu mendapatkan +3 Agra."
                            }
                        )
                        
                    except errors.FloodWait as e:
                        log.warning(f"FloodWait: sleeping for {e.value} seconds")
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        log.error(f"Error reading story {link}: {e}")
                        await conn.execute("UPDATE promo_verifications SET status = 'ERROR' WHERE id = ?", (req_id,))
                        await conn.commit()
                        import requests
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": main_user_id,
                                "text": f"❌ Gagal memvalidasi link {link}\n\nTerjadi kesalahan sistem saat mencoba membaca Story-mu. Pastikan akun tidak di-private atau silakan hubungi admin jika ini terus terjadi."
                            }
                        )

                else:
                    # LPM Logic
                    match = re.search(r"t\.me/([^/]+)/(\d+)", link)
                    if not match:
                        await conn.execute("UPDATE promo_verifications SET status = 'INVALID_URL' WHERE id = ?", (req_id,))
                        await conn.commit()
                        import requests
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": main_user_id,
                                "text": f"❌ Gagal memvalidasi link {link}\n\nFormat link tidak dikenali. Pastikan itu adalah link ke spesifik pesan (contoh: https://t.me/GrupName/123)"
                            }
                        )
                        continue
                        
                    chat_id = match.group(1)
                    msg_id = int(match.group(2))
                    
                    if chat_id == "c":
                        await conn.execute("UPDATE promo_verifications SET status = 'PRIVATE_GROUP_NOT_SUPPORTED' WHERE id = ?", (req_id,))
                        await conn.commit()
                        import requests
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": main_user_id,
                                "text": f"❌ Gagal memvalidasi link {link}\n\nLink dari grup Private tidak dapat dibaca oleh bot. Pastikan promosi dilakukan di Grup Publik."
                            }
                        )
                        continue

                    try:
                        msg = await app.get_messages(chat_id, msg_id)
                        if not msg or msg.empty:
                            await conn.execute("UPDATE promo_verifications SET status = 'NOT_FOUND' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nPesan tidak ditemukan atau grup tersebut bersifat private/tidak bisa diakses oleh bot."
                                }
                            )
                            continue
                            
                        text = msg.text or msg.caption or ""
                        sender_id = msg.from_user.id if msg.from_user else None
                        
                        if lpm_keyword.lower() not in text.lower():
                            await conn.execute("UPDATE promo_verifications SET status = 'NO_KEYWORD' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nSepertinya bukan teks promosi yang sesuai. (Tidak mengandung kata '{lpm_keyword}')"
                                }
                            )
                            continue
                            
                        valid_sender = False
                        if sender_id == main_user_id:
                            valid_sender = True
                        else:
                            linked_accounts = await db.get_linked_accounts(conn, main_user_id)
                            if sender_id in linked_accounts:
                                valid_sender = True
                                
                        if not valid_sender:
                            await conn.execute("UPDATE promo_verifications SET status = 'SENDER_MISMATCH' WHERE id = ?", (req_id,))
                            await conn.commit()
                            import requests
                            requests.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={
                                    "chat_id": main_user_id,
                                    "text": f"❌ Gagal memvalidasi link {link}\n\nPengirim pesan bukan akun utamamu dan bukan dari Akun Kerja yang sudah ditautkan."
                                }
                            )
                            continue
                            
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
            
        # Process userbot requests
        await process_userbot_requests(conn)
            
        # Polling delay
        await asyncio.sleep(2)

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
