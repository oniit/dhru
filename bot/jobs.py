import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from bot.settings import ROOT, BACKUP_CH_ID, PRESENCE_CH_ID, EDITOR_GID

async def daily_staff_attendance_open(context, opened_by=0):
    if not PRESENCE_CH_ID: return
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    
    sid = await db.open_attendance_session(
        conn,
        class_id="staff_auto",
        title="Presensi Harian Staf",
        opened_by=opened_by, # 0 = Bot, >0 = Admin (testauto)
        chat_id=PRESENCE_CH_ID,
    )
    
    # Kirim pesan perdana ke channel
    try:
        msg = await context.bot.send_message(
            chat_id=PRESENCE_CH_ID,
            text="Membuka sesi presensi otomatis...",
        )
        await db.set_attendance_announce_message(conn, sid, msg.message_id)
    except Exception as e:
        print("Gagal mengirim pesan presensi ke channel:", e)
        return
        
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



async def daily_auto_close_tasks(context):
    db = context.application.bot_data.get("db")
    conn = context.application.bot_data.get("conn")
    if not db or not conn: return
    closed_ids = await db.auto_close_stale_tasks(conn)
    if closed_ids:
        print(f"Auto-closed {len(closed_ids)} stale tasks.")


import json\nimport html
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

def setup_jobs(application: Application):
    jq = application.job_queue
    if not jq: return
    
    # Gunakan timezone WIB (UTC+7) secara eksplisit agar jadwal tidak bergeser
    wib = datetime.timezone(datetime.timedelta(hours=7))
    
    # Run daily at midnight WIB\n    jq.run_daily(daily_birthday_reminder, datetime.time(hour=8, minute=0, second=0, tzinfo=wib))\n    
    jq.run_daily(daily_auto_close_tasks, datetime.time(hour=0, minute=0, second=0, tzinfo=wib))


    if PRESENCE_CH_ID:
        # Buka presensi jam 07:00 WIB
        jq.run_daily(daily_staff_attendance_open, datetime.time(hour=7, minute=0, second=0, tzinfo=wib))
        # Tutup presensi jam 23:59 WIB
        jq.run_daily(daily_staff_attendance_close, datetime.time(hour=23, minute=59, second=0, tzinfo=wib))
