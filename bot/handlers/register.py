"""Register all handlers on the Application."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, MessageReactionHandler, filters

from bot.database import Database

from . import attendance, commands, ktm, karpeg, kontrak, messages, triggers, broadcast, tugas, menfess, games



def register_all(application: Application, db: Database) -> None:
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", commands.cmd_start))
    application.add_handler(CommandHandler("help", commands.cmd_help))
    application.add_handler(CommandHandler("profile", commands.cmd_profile))
    application.add_handler(CommandHandler("profile_dtl", commands.cmd_profile_dtl))
    application.add_handler(CommandHandler("profil", commands.cmd_profile))
    application.add_handler(CommandHandler("lengkapi", commands.cmd_lengkapi))
    application.add_handler(CommandHandler("kode", commands.cmd_kode))
    application.add_handler(CommandHandler("tugas", tugas.cmd_tugas_router))
    application.add_handler(CommandHandler("ktm", ktm.cmd_ktm))
    application.add_handler(CommandHandler("ktm_foto", ktm.cmd_ktm_foto))
    application.add_handler(CommandHandler("karpeg", karpeg.cmd_karpeg))
    application.add_handler(CommandHandler("karpeg_foto", karpeg.cmd_karpeg_foto))
    application.add_handler(CommandHandler("ubah", commands.cmd_ubah))
    application.add_handler(CommandHandler("add", commands.cmd_add))
    application.add_handler(CommandHandler("transfer", commands.cmd_transfer))
    application.add_handler(CommandHandler("agralog", commands.cmd_agralog))
    application.add_handler(CommandHandler("setrole", commands.cmd_setrole))
    application.add_handler(CommandHandler("owner_reset", commands.cmd_owner_reset))
    application.add_handler(CommandHandler("daftar", commands.cmd_daftar))
    application.add_handler(CommandHandler("maba", commands.cmd_maba))
    application.add_handler(CommandHandler("detail", commands.cmd_detail))
    application.add_handler(CommandHandler("admin_data", commands.cmd_admin_data))
    application.add_handler(CommandHandler("pending", commands.cmd_pending))
    application.add_handler(CommandHandler("log", commands.cmd_log))
    application.add_handler(CommandHandler("tagall", commands.cmd_tagall))
    application.add_handler(CommandHandler("all", commands.cmd_all))
    application.add_handler(CommandHandler("pindah_data", commands.cmd_pindah_data))
    application.add_handler(CommandHandler("cek_user", commands.cmd_cek_user))
    application.add_handler(CommandHandler("orreset_user", commands.cmd_orreset_user))
    application.add_handler(CommandHandler("orreset_agra", commands.cmd_orreset_agra))
    application.add_handler(CommandHandler("addtag", commands.cmd_addtag))
    application.add_handler(CommandHandler("users", commands.cmd_users))
    application.add_handler(CommandHandler("reload", commands.cmd_reload))
    
    # Routers
    application.add_handler(CommandHandler("presensi", attendance.cmd_presensi_router))
    application.add_handler(CommandHandler("trigger", triggers.cmd_trigger_router))
    application.add_handler(CommandHandler("agra", commands.cmd_agra_router))
    application.add_handler(CommandHandler("hadir", attendance.cmd_hadir))
    
    # Games
    application.add_handler(CommandHandler("atur", games.cmd_atur))
    application.add_handler(CommandHandler("bermain", games.cmd_bermain))
    application.add_handler(CommandHandler("status", games.cmd_status))
    application.add_handler(CommandHandler("berhenti", games.cmd_berhenti))
    application.add_handler(CommandHandler("hasil", games.cmd_hasil))
    application.add_handler(CommandHandler("tebak", games.cmd_tebak))
    
    # New handlers
    application.add_handler(CommandHandler("kontrak", kontrak.cmd_kontrak_router))
    application.add_handler(CommandHandler("gencode", commands.cmd_gencode))
    application.add_handler(CommandHandler("gencode_avail", commands.cmd_gencode_avail))
    application.add_handler(CommandHandler("broadcast", broadcast.cmd_broadcast))
    application.add_handler(CommandHandler("menfess_read", menfess.cmd_menfess_read))
    application.add_handler(menfess.cmd_menfess_router, group=1)

    from .promo import setup_promo_handlers
    setup_promo_handlers(application)

    from telegram.ext import ChatMemberHandler, ChatJoinRequestHandler
    application.add_handler(ChatMemberHandler(messages.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatJoinRequestHandler(messages.on_chat_join_request))
    
    application.add_handler(CommandHandler("kick", commands.cmd_kick))
    application.add_handler(CallbackQueryHandler(commands.on_kick_callback, pattern="^kick:"))
    
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
            ~filters.COMMAND & filters.ChatType.PRIVATE,
            messages.on_private_message,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS,
            messages.on_group_message,
        ),
        group=2,
    )
    
    application.add_handler(MessageReactionHandler(games.on_message_reaction))
    
    # Optional: fallback for unhandled commands (uncomment if desired)
    # application.add_handler(MessageHandler(filters.COMMAND, commands.cmd_unknown))
    
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, messages.global_profile_tracker), group=-1)
