async def cmd_cekbalas(update, context):
    import re
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("Reply pesan bot dulu dengan /cekbalas")
        return
    bot_text = reply.text or reply.caption or ""
    matches = re.findall(r"#ID_(\d+)", bot_text)
    is_bot = reply.from_user and reply.from_user.id == context.bot.id
    msg = (
        f"Chat ID: {update.effective_chat.id}\n"
        f"Reply from Bot: {is_bot}\n"
        f"Matches: {matches}\n"
        f"Bot Text length: {len(bot_text)}\n"
        f"Text Preview: {bot_text[:100]}"
    )
    await update.message.reply_text(msg)
