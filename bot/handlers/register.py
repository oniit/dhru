"""Register all handlers on the Application."""

from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.database import Database

from . import attendance, commands, messages, triggers, broadcast


def register_all(application: Application, db: Database) -> None:
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", commands.cmd_start))
    application.add_handler(CommandHandler("help", commands.cmd_help))
    application.add_handler(CommandHandler("profile", commands.cmd_profile))
    application.add_handler(CommandHandler("profil", commands.cmd_profile))
    application.add_handler(CommandHandler("lengkapi", commands.cmd_lengkapi))
    application.add_handler(CommandHandler("ubah", commands.cmd_ubah))
    application.add_handler(CommandHandler("add", commands.cmd_add))
    application.add_handler(CommandHandler("setrole", commands.cmd_setrole))
    application.add_handler(CommandHandler("owner_reset", commands.cmd_owner_reset))
    application.add_handler(CommandHandler("daftar", commands.cmd_daftar))
    application.add_handler(CommandHandler("admin_data", commands.cmd_admin_data))
    application.add_handler(CommandHandler("pending", commands.cmd_pending))
    application.add_handler(CommandHandler("log", commands.cmd_log))
    application.add_handler(CommandHandler("tagall", commands.cmd_tagall))
    application.add_handler(CommandHandler("all", commands.cmd_tagall))
    application.add_handler(CommandHandler("buka_presensi", attendance.cmd_buka_presensi))
    application.add_handler(CommandHandler("tutup_presensi", attendance.cmd_tutup_presensi))
    application.add_handler(CommandHandler("hadir", attendance.cmd_hadir))
    application.add_handler(CommandHandler("top_agra", commands.cmd_top_agra))
    application.add_handler(CommandHandler("rekap_hadir", attendance.cmd_rekap_hadir))
    application.add_handler(CommandHandler("sesi", attendance.cmd_sesi_aktif))
    
    # New handlers
    application.add_handler(CommandHandler("gencode", commands.cmd_gencode))
    
    application.add_handler(CommandHandler("addtrigger", triggers.cmd_addtrigger))
    application.add_handler(CommandHandler("deltrigger", triggers.cmd_deltrigger))
    application.add_handler(CommandHandler("listtrigger", triggers.cmd_listtrigger))
    application.add_handler(CommandHandler("selesai_trigger", triggers.cmd_selesai_trigger))
    
    application.add_handler(CommandHandler("broadcast", broadcast.cmd_broadcast))

    application.add_handler(CallbackQueryHandler(commands.on_callback))
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
            messages.track_group_activity,
        ),
        group=0,
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            messages.on_text,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & filters.REPLY,
            messages.on_group_text,
        ),
        group=2,
    )
