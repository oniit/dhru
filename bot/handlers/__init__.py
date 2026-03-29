from telegram.ext import Application

from bot.database import Database

from .register import register_all


def setup_handlers(application: Application, db: Database) -> None:
    register_all(application, db)
