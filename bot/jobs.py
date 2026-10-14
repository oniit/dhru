import os
import datetime
import html
import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from bot.settings import ROOT, BACKUP_CH_ID, PRESENCE_CH_ID, EDITOR_GID

log = logging.getLogger(__name__)

async def daily_staff_attendance_open(context, opened_by=None):
    if not PRESENCE_CH_ID: return
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    if opened_by is None:
        from bot.settings import OWNER_ID
        opened_by = OWNER_ID

    existing_sess = await db.get_open_session_for_class(conn, "staff_auto")
    if existing_sess:
        print(f"Sesi presensi staff_auto sudah aktif (ID: {existing_sess['id']}), melewati pembuatan sesi baru.")
        return existing_sess["id"]

    sid = await db.open_attendance_session(
        conn,
        class_id="staff_auto",
        title="Presensi Harian Staf",
        opened_by=opened_by,
        chat_id=PRESENCE_CH_ID,
    )
    
    # Kirim pesan perdana ke channel
    import asyncio
    msg = None
    for attempt in range(3):
        try:
            msg = await context.bot.send_message(
                chat_id=PRESENCE_CH_ID,
                text="Membuka sesi presensi otomatis...",
            )
            await db.set_attendance_announce_message(conn, sid, msg.message_id)
            break
        except Exception as e:
            print(f"Gagal mengirim pesan presensi ke channel (percobaan {attempt+1}):", e)
            if attempt < 2:
                await asyncio.sleep(5)
        
    # Import locally to avoid circular imports if any
    from bot.handlers.attendance import refresh_auto_presensi_announcement
    await refresh_auto_presensi_announcement(context, db, conn, sid)
    
    staff_ids = await db.get_all_staff_ids(conn)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Hadir", callback_data=f"sh:{sid}")]])
    
    for uid in staff_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="🔔 *Presensi Harian Staf*\n\nSilakan klik tombol di bawah ini untuk mencatatkan kehadiran Anda hari ini.",
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)
            
    return sid

async def daily_staff_attendance_close(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    sess = await db.get_open_session_for_class(conn, "staff_auto")
    if not sess: return
    
    await db.close_attendance_session(conn, sess["id"])
    
    from bot.handlers.attendance import refresh_auto_presensi_announcement
    await refresh_auto_presensi_announcement(context, db, conn, sess["id"])



async def periodic_auto_close_attendance(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    try:
        timeout_sec = int(os.environ.get("PRESENSI_AUTOCLOSE_TIMEOUT", "7200"))
        closed_ids = await db.auto_close_stale_sessions(conn, timeout_seconds=timeout_sec)
        if closed_ids:
            print(f"Auto-closed {len(closed_ids)} stale attendance sessions: {closed_ids}")
            from bot.handlers.attendance import refresh_presensi_announcement
            for sid in closed_ids:
                try:
                    await refresh_presensi_announcement(context, db, conn, sid)
                except Exception as e:
                    print(f"Failed to refresh announcement for auto-closed session #{sid}: {e}")
    except Exception as e:
        print(f"Error in periodic_auto_close_attendance: {e}")



async def daily_auto_close_tasks(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    try:
        closed_ids = await db.auto_close_stale_tasks(conn)
        if closed_ids:
            print(f"Auto-closed {len(closed_ids)} stale tasks.")
    except Exception as e:
        print(f"Error in daily_auto_close_tasks: {e}")


import json
import html
from bot.timefmt import days_until_next_birthday, get_today_wib

async def daily_birthday_reminder(context):
    if not EDITOR_GID: return
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    cur = await conn.execute("SELECT telegram_id, username, first_name, last_name, profile_json FROM users")
    rows = await cur.fetchall()
    
    upcoming = []
    for r in rows:
        p = json.loads(r["profile_json"] or "{}")
        bdate = p.get("birth_date")
        if not bdate: continue
        
        dist = days_until_next_birthday(bdate)
        if dist == 3:
            name = (p.get("full_name") or f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "—")
            upcoming.append((name, r["username"]))
            
    if upcoming:
        lines = ["🎂 <b>Pengingat Ulang Tahun H-3!</b>\n"]
        for name, un in upcoming:
            un_str = f" (@{html.escape(un)})" if un else ""
            lines.append(f"• {html.escape(name)}{un_str}")
        lines.append("\nMari siapkan sesuatu untuk mereka!")
        
        try:
            await context.bot.send_message(
                chat_id=EDITOR_GID,
                text="\n".join(lines),
                parse_mode="HTML"
            )
        except Exception as e:
            print("Gagal kirim reminder ultah:", e)

async def daily_maba_attendance_open(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    ospek_mode = await db.get_setting(conn, "ospek_mode", "off")
    if ospek_mode != "on":
        return

    from bot.settings import OWNER_ID, MABA_GROUP_GIDS, OSPEK_GID
    if not OSPEK_GID: return

    existing_sess = await db.get_open_session_for_class(conn, "maba_auto")
    if existing_sess:
        print(f"Sesi presensi maba_auto sudah aktif (ID: {existing_sess['id']}), melewati pembuatan sesi baru.")
        return existing_sess["id"]

    sid = await db.open_attendance_session(
        conn,
        class_id="maba_auto",
        title="🔔 Presensi Harian Pravesa",
        opened_by=OWNER_ID,
        chat_id=OSPEK_GID,
    )
    
    import asyncio
    msg = None
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Hadir", callback_data=f"sh:{sid}")]])
    
    for attempt in range(3):
        try:
            msg = await context.bot.send_message(
                chat_id=OSPEK_GID,
                text="Membuka sesi presensi otomatis maba...",
                reply_markup=kb,
            )
            await db.set_attendance_announce_message(conn, sid, msg.message_id)
            break
        except Exception as e:
            print(f"Gagal mengirim presensi general ke OSPEK_GID {OSPEK_GID} (percobaan {attempt+1}): {e}")
            if attempt < 2:
                import asyncio
                await asyncio.sleep(5)
    
    extra_data = {}
    for i, gid in enumerate(MABA_GROUP_GIDS):
        try:
            group_msg = await context.bot.send_message(
                chat_id=gid,
                text="🔔 *Presensi Harian Ospek*\n\nSilakan klik tombol di bawah ini untuk mencatatkan kehadiran Anda hari ini.",
                parse_mode="Markdown",
                reply_markup=kb
            )
            extra_data[str(i + 1)] = {"chat_id": gid, "msg_id": group_msg.message_id}
        except Exception:
            pass
        await asyncio.sleep(0.1)

    import json
    await db.set_attendance_extra_data(conn, sid, json.dumps(extra_data))

    from bot.handlers.attendance import refresh_maba_presensi_announcement
    await refresh_maba_presensi_announcement(context, db, conn, sid)
    
    return sid


async def daily_maba_attendance_close(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    sess = await db.get_open_session_for_class(conn, "maba_auto")
    if not sess: return
    
    await db.close_attendance_session(conn, sess["id"])
    
    from bot.handlers.attendance import refresh_maba_presensi_announcement
    await refresh_maba_presensi_announcement(context, db, conn, sess["id"])

async def process_broadcast_queue(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    job = await db.get_pending_broadcast_job(conn)
    if not job: return

    job_id = job["id"]
    msg_text = job["message_text"]
    reporter_id = job["reporter_id"]
    try:
        targets = json.loads(job["target_users_json"])
        processed = set(json.loads(job["processed_users_json"]))
    except Exception:
        await db.update_broadcast_job(conn, job_id, [], "failed")
        return

    remaining = [u for u in targets if u not in processed]
    if not remaining:
        await db.update_broadcast_job(conn, job_id, list(processed), "completed")
        if reporter_id:
            try:
                await context.bot.send_message(
                    chat_id=reporter_id,
                    text=f"✅ Broadcast {job_id} selesai.\nBerhasil/Diproses: {len(processed)} user."
                )
            except Exception: pass
        return

    # Process a batch of 30
    batch = remaining[:30]
    success_in_batch = 0
    from telegram.error import RetryAfter, BadRequest
    import asyncio

    for uid in batch:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=msg_text,
                parse_mode="HTML"
            )
            success_in_batch += 1
            processed.add(uid)
        except RetryAfter as e:
            # Stop batch, will retry next run
            break
        except BadRequest as e:
            err_str = str(e).lower()
            if "can't parse entities" in err_str or "entity" in err_str:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=msg_text,
                    )
                    success_in_batch += 1
                except Exception as inner_e:
                    log.warning("Broadcast to %s failed after plain text fallback: %s", uid, inner_e)
            else:
                log.warning("Broadcast to %s failed (BadRequest): %s", uid, e)
            processed.add(uid)
        except Exception as e:
            # Mark as processed even if failed to avoid infinite loop
            log.warning("Broadcast to %s failed: %s", uid, e)
            processed.add(uid)
        await asyncio.sleep(0.05)

    status = "completed" if len(processed) >= len(targets) else "pending"
    await db.update_broadcast_job(conn, job_id, list(processed), status)
    
    if status == "completed" and reporter_id:
        try:
            await context.bot.send_message(
                chat_id=reporter_id,
                text=f"✅ Broadcast {job_id} selesai.\nDiproses: {len(processed)} user."
            )
        except Exception: pass

def is_keep_msg_excluded(msg, bot_id: int | None = None) -> bool:
    """
    Menentukan apakah pesan di KEEP_CH_ID harus diabaikan dan tidak diforward ke POST_CH_ID.
    Semua jenis pesan (teks, media, poll, dokumen, stiker, dll) TETAP diforward,
    KECUALI pesan bot (notifikasi sukses/error) dan pesan servis sistem Telegram.
    """
    # 1. Abaikan jika pesan kosong/terhapus atau pesan servis Telegram (pin pesan, ubah foto ch, dll)
    if getattr(msg, "empty", False) or getattr(msg, "service", False):
        return True

    # 2. Jika pengirim teridentifikasi sebagai bot
    from_user = getattr(msg, "from_user", None)
    if from_user:
        if getattr(from_user, "is_bot", False):
            return True
        if bot_id and getattr(from_user, "id", None) == bot_id:
            return True

    # 3. Cek teks template spesifik yang dikirim oleh bot ini sendiri
    text_content = (getattr(msg, "text", "") or getattr(msg, "caption", "") or "").lower()
    if "cek @dhruvaposter" in text_content or "terjadi kesalahan saat mem-forward pesan" in text_content:
        return True

    # Semua pesan lainnya tetap diforward!
    return False


async def daily_keep_to_post(context):
    import logging
    log = logging.getLogger(__name__)
    
    from bot.settings import BOT_TOKEN, API_ID, API_HASH, KEEP_CH_ID, POST_CH_ID
    if not KEEP_CH_ID or not POST_CH_ID or not API_ID or not API_HASH:
        log.warning("Missing config for KEEP to POST forwarder")
        return

    bot_id = int(BOT_TOKEN.split(":")[0]) if BOT_TOKEN and ":" in BOT_TOKEN else None

    from pyrogram import Client
    import asyncio

    USERBOT_SESSION = os.environ.get("USERBOT_SESSION", "").strip()
    
    if USERBOT_SESSION:
        app = Client("keep_forwarder", session_string=USERBOT_SESSION, api_id=API_ID, api_hash=API_HASH, in_memory=True)
    else:
        # Fallback menggunakan file checker.session (rawan database is locked jika checker.py jalan bersamaan)
        app = Client("checker", api_id=API_ID, api_hash=API_HASH)
    
    try:
        await app.start()
    except Exception as e:
        log.error(f"Failed to start Pyrogram for keep_to_post: {e}")
        return

    try:
        message_ids = []
        async for msg in app.get_chat_history(KEEP_CH_ID):
            # Abaikan pesan notifikasi dan error bot agar tidak ikut ter-forward ke POST_CH_ID
            if is_keep_msg_excluded(msg, bot_id=bot_id):
                continue
            message_ids.append(msg.id)
            
        if not message_ids:
            return
            
        message_ids.reverse()

        forwarded_count = 0
        chunk_size = 100
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i:i + chunk_size]
            try:
                await app.forward_messages(
                    chat_id=POST_CH_ID,
                    from_chat_id=KEEP_CH_ID,
                    message_ids=chunk
                )
                forwarded_count += len(chunk)
            except Exception as fe:
                log.warning(f"Batch forward failed ({fe}), falling back to single-message forwarding")
                for mid in chunk:
                    try:
                        await app.forward_messages(
                            chat_id=POST_CH_ID,
                            from_chat_id=KEEP_CH_ID,
                            message_ids=[mid]
                        )
                        forwarded_count += 1
                        await asyncio.sleep(0.3)
                    except Exception as single_e:
                        log.warning(f"Skipping unforwardable message {mid}: {single_e}")
            if i + chunk_size < len(message_ids):
                await asyncio.sleep(2)

        if forwarded_count > 0:
            log.info(f"Successfully forwarded {forwarded_count} messages.")
            try:
                await context.bot.send_message(
                    chat_id=KEEP_CH_ID,
                    text=f"✅ <b>Cek @DhruvaPoster</b>, {forwarded_count} pesan di atas telah diforward ke sana.",
                    parse_mode="HTML"
                )
            except Exception: pass
        else:
            log.error("Failed to forward any messages in keep_to_post.")
            try:
                await context.bot.send_message(
                    chat_id=KEEP_CH_ID,
                    text="❌ <b>Gagal!</b> Seluruh pesan tidak dapat di-forward.",
                    parse_mode="HTML"
                )
            except Exception: pass
                
    except Exception as e:
        import traceback
        log.error(f"Error in keep_to_post loop: {e}\n{traceback.format_exc()}")
    finally:
        await app.stop()

async def process_promo_queue(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn:
        return

    try:
        cur = await conn.execute("SELECT * FROM promo_verifications WHERE status = 'PENDING'")
        rows = await cur.fetchall()
        if not rows:
            return

        from bot.handlers.promo import verify_lpm_link_embed
        lpm_keyword = await db.get_setting(conn, "promo_lpm_keyword", "dhruva")

        for row in rows:
            req_id = row["id"]
            user_id = row["user_id"]
            link = row["link"]
            promo_type = row.get("promo_type", "lpm")
            created_at = row["created_at"]

            # Expiration (2 days)
            if time.time() - created_at > 2 * 24 * 3600:
                await conn.execute("UPDATE promo_verifications SET status = 'EXPIRED' WHERE id = ?", (req_id,))
                await conn.commit()
                continue

            # Atomic claim: transition from PENDING -> PROCESSING
            cur_lock = await conn.execute(
                "UPDATE promo_verifications SET status = 'PROCESSING' WHERE id = ? AND status = 'PENDING'",
                (req_id,)
            )
            await conn.commit()
            if getattr(cur_lock, "rowcount", 1) == 0:
                continue

            if promo_type == "lpm":
                is_valid, status_code, err_msg = await verify_lpm_link_embed(conn, db, user_id, link, lpm_keyword)
                if is_valid:
                    cur_v = await conn.execute("UPDATE promo_verifications SET status = 'VALID' WHERE id = ? AND status = 'PROCESSING'", (req_id,))
                    if getattr(cur_v, "rowcount", 1) > 0:
                        await db.add_agra(
                            conn,
                            target_id=user_id,
                            actor_id=user_id,
                            amount=1,
                            description="Reward promosi LPM",
                            chat_id=None,
                            message_id=None,
                        )
                        await conn.commit()
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"✅ <b>Link LPM kamu berhasil divalidasi!</b>\n\n"
                                    f"🔗 <code>{html.escape(link)}</code>\n\n"
                                    f"🎁 Kamu mendapatkan <b>+1 Agra</b>."
                                ),
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                        except Exception as e:
                            log.warning("Gagal kirim notif promo valid ke %s: %s", user_id, e)
                elif status_code not in ("NETWORK_ERROR",):
                    await conn.execute("UPDATE promo_verifications SET status = ? WHERE id = ?", (status_code, req_id))
                    await conn.commit()
                    if err_msg:
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"❌ <b>Gagal Memvalidasi Link LPM</b>\n\n"
                                    f"🔗 <code>{html.escape(link)}</code>\n\n"
                                    f"<b>Alasan:</b>\n{err_msg}"
                                ),
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                        except Exception as e:
                            log.warning("Gagal kirim notif promo gagal ke %s: %s", user_id, e)
                else:
                    # NETWORK_ERROR: rollback back to PENDING so next tick can retry
                    await conn.execute("UPDATE promo_verifications SET status = 'PENDING' WHERE id = ?", (req_id,))
                    await conn.commit()
    except Exception as e:
        log.error("Error in process_promo_queue: %s", e)

def setup_jobs(application: Application):
    jq = application.job_queue
    if not jq: return
    
    from zoneinfo import ZoneInfo
    
    wib = ZoneInfo("Asia/Jakarta")
    
    # Run daily at midnight WIB
    jq.run_daily(daily_birthday_reminder, datetime.time(hour=8, minute=0, second=0, tzinfo=wib))
    jq.run_daily(daily_auto_close_tasks, datetime.time(hour=0, minute=0, second=0, tzinfo=wib))

    # Background queue
    jq.run_repeating(process_broadcast_queue, interval=10, first=10)
    jq.run_repeating(process_promo_queue, interval=10, first=5)
    jq.run_repeating(periodic_auto_close_attendance, interval=60, first=15)


    if PRESENCE_CH_ID:
        # Buka presensi jam 07:00 WIB
        jq.run_daily(daily_staff_attendance_open, datetime.time(hour=7, minute=0, second=0, tzinfo=wib))
        # Tutup presensi jam 23:59 WIB
        jq.run_daily(daily_staff_attendance_close, datetime.time(hour=23, minute=59, second=0, tzinfo=wib))
        
        jq.run_daily(daily_maba_attendance_open, datetime.time(hour=15, minute=40, second=0, tzinfo=wib))
        jq.run_daily(daily_maba_attendance_close, datetime.time(hour=22, minute=0, second=0, tzinfo=wib))

    from bot.settings import KEEP_CH_ID, POST_CH_ID
    if KEEP_CH_ID and POST_CH_ID:
        jq.run_daily(daily_keep_to_post, datetime.time(hour=15, minute=1, second=0, tzinfo=wib))
