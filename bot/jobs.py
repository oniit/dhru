import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from bot.settings import ROOT, BACKUP_CH_ID, PRESENCE_CH_ID

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

async def daily_backup(context):
    if not BACKUP_CH_ID: return
    db_path = ROOT / "data" / "bot.db"
    if not db_path.exists(): return
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(db_path, "rb") as f:
            await context.bot.send_document(
                chat_id=BACKUP_CH_ID, 
                document=f, 
                filename=f"bot_backup_{now.replace(':', '-')}.db",
                caption=f"Daily Database Backup - {now}"
            )
    except Exception as e:
        print("Failed to send DB backup:", e)

def setup_jobs(application: Application):
    jq = application.job_queue
    if not jq: return
    
    if BACKUP_CH_ID:
        jq.run_daily(daily_backup, datetime.time(hour=0, minute=0, second=0))
        
    if PRESENCE_CH_ID:
        # 00:00 UTC = 07:00 WIB
        jq.run_daily(daily_staff_attendance_open, datetime.time(hour=0, minute=0, second=0))
        # 16:59 UTC = 23:59 WIB
        jq.run_daily(daily_staff_attendance_close, datetime.time(hour=16, minute=59, second=0))
