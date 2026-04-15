import datetime
from telegram.ext import Application
from bot.settings import ROOT, BACKUP_CHANNEL_ID

async def daily_backup(context):
    if not BACKUP_CHANNEL_ID: return
    db_path = ROOT / "data" / "bot.db"
    if not db_path.exists(): return
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(db_path, "rb") as f:
            await context.bot.send_document(
                chat_id=BACKUP_CHANNEL_ID, 
                document=f, 
                filename=f"bot_backup_{now.replace(':', '-')}.db",
                caption=f"Daily Database Backup - {now}"
            )
    except Exception as e:
        print("Failed to send DB backup:", e)

def setup_jobs(application: Application):
    if BACKUP_CHANNEL_ID:
        jq = application.job_queue
        if jq:
            jq.run_daily(daily_backup, datetime.time(hour=0, minute=0, second=0))
