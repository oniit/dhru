"""Register all handlers on the Application."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.database import Database

from . import attendance, commands, ktm, karpeg, messages, triggers, broadcast


async def cmd_presensi_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Menu Presensi:\n/presensi buka\n/presensi tutup\n/presensi sesi\n/presensi rekap\n/presensi hadir")
        return
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "buka": await attendance.cmd_buka_presensi(update, context)
        elif subcmd == "tutup": await attendance.cmd_tutup_presensi(update, context)
        elif subcmd == "sesi": await attendance.cmd_sesi_aktif(update, context)
        elif subcmd == "rekap": await attendance.cmd_rekap_hadir(update, context)
        elif subcmd == "hadir": await attendance.cmd_hadir(update, context)
        else: await update.message.reply_text("Sub-command tidak ditemukan.")
    finally:
        context.args = original_args


async def cmd_trigger_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Menu Trigger:\n/trigger add\n/trigger list\n/trigger done\n/trigger del")
        return
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "add": await triggers.cmd_addtrigger(update, context)
        elif subcmd == "list": await triggers.cmd_listtrigger(update, context)
        elif subcmd == "done": await triggers.cmd_selesai_trigger(update, context)
        elif subcmd in ("del", "delete"): await triggers.cmd_deltrigger(update, context)
        else: await update.message.reply_text("Sub-command tidak ditemukan.")
    finally:
        context.args = original_args


async def cmd_agra_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Menu Agra:\n/agra top\n/agra log")
        return
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "top": await commands.cmd_agratop(update, context)
        elif subcmd == "log": await commands.cmd_agralog(update, context)
        else: await update.message.reply_text("Sub-command tidak ditemukan.")
    finally:
        context.args = original_args

def register_all(application: Application, db: Database) -> None:
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", commands.cmd_start))
    application.add_handler(CommandHandler("help", commands.cmd_help))
    application.add_handler(CommandHandler("profile", commands.cmd_profile))
    application.add_handler(CommandHandler("profil", commands.cmd_profile))
    application.add_handler(CommandHandler("lengkapi", commands.cmd_lengkapi))
    application.add_handler(
        CommandHandler("ktm", ktm.cmd_ktm, filters=ktm.KT_PRIVATE),
    )
    application.add_handler(
        CommandHandler("ktm_foto", ktm.cmd_ktm_foto, filters=ktm.KT_PRIVATE),
    )
    application.add_handler(
        CommandHandler("karpeg", karpeg.cmd_karpeg, filters=karpeg.KARPEG_PRIVATE),
    )
    application.add_handler(
        CommandHandler("karpeg_foto", karpeg.cmd_karpeg_foto, filters=karpeg.KARPEG_PRIVATE),
    )
    application.add_handler(CommandHandler("ubah", commands.cmd_ubah))
    application.add_handler(CommandHandler("add", commands.cmd_add))
    application.add_handler(CommandHandler("transfer", commands.cmd_transfer))
    application.add_handler(CommandHandler("agralog", commands.cmd_agralog))
    application.add_handler(CommandHandler("setrole", commands.cmd_setrole))
    application.add_handler(CommandHandler("owner_reset", commands.cmd_owner_reset))
    application.add_handler(CommandHandler("daftar", commands.cmd_daftar))
    application.add_handler(CommandHandler("list_id", commands.cmd_list_id))
    application.add_handler(CommandHandler("admin_data", commands.cmd_admin_data))
    application.add_handler(CommandHandler("pending", commands.cmd_pending))
    application.add_handler(CommandHandler("log", commands.cmd_log))
    application.add_handler(CommandHandler("tagall", commands.cmd_tagall))
    application.add_handler(CommandHandler("all", commands.cmd_tagall))
    
    # Routers
    application.add_handler(CommandHandler("presensi", cmd_presensi_router))
    application.add_handler(CommandHandler("trigger", cmd_trigger_router))
    application.add_handler(CommandHandler("agra", cmd_agra_router))
    application.add_handler(CommandHandler("hadir", attendance.cmd_hadir))
    
    # New handlers
    application.add_handler(CommandHandler("gencode", commands.cmd_gencode))
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
            filters.PHOTO & filters.ChatType.PRIVATE,
            ktm.on_ktm_photo,
            block=False,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            filters.PHOTO & filters.ChatType.PRIVATE,
            karpeg.on_karpeg_photo,
            block=False,
        ),
        group=1,
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
