"""
Entry point: Telegram bot (profil, Agra, presensi, role).

Salin .env.example -> .env, isi BOT_TOKEN dan OWNER_ID.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram.ext import Application

from bot.database import Database
from bot.handlers import setup_handlers
from bot.handlers.common import sync_roles_from_env
from bot.settings import BOT_TOKEN, BACKUP_CH_ID

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    


    conn = await db.connect()
    await sync_roles_from_env(db, conn)
    application.bot_data["conn"] = conn
    log.info("Database siap.")

    import os, json
    if os.path.exists(".restart.json"):
        try:
            with open(".restart.json", "r") as f:
                data = json.load(f)
            await application.bot.edit_message_text(
                "✅ <b>Bot siap digunakan!</b>",
                chat_id=data["chat_id"],
                message_id=data["message_id"],
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Gagal mengirim notif selesai restart: %s", e)
        finally:
            try:
                os.remove(".restart.json")
            except Exception:
                pass


async def post_shutdown(application: Application) -> None:
    conn = application.bot_data.get("conn")
    if conn:
        await conn.close()
        log.info("Koneksi database ditutup.")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN kosong. Buat file .env di folder proyek (lihat .env.example)."
        )
    db = Database()
    from telegram.ext import Defaults
    from telegram.constants import ParseMode
    defaults = Defaults(parse_mode=ParseMode.HTML)
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["db"] = db
    from bot.jobs import setup_jobs
    setup_jobs(application)
    setup_handlers(application, db)
    log.info("Polling dimulai…")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
