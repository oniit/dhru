async def cmd_cekbalas(update, context):
    import re
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("Reply pesan bot dulu dengan /cekbalas")
        return
    bot_text = reply.text or reply.caption or ""
    matches = re.findall(r"#ID_(\d+)", bot_text)
    is_bot = reply.from_user and reply.from_user.id == context.bot.id
    
    # Check if the command itself has arguments simulating #balas text
    # e.g. /cekbalas #balas halo
    test_text = update.message.text.replace("/cekbalas", "").strip()
    if not test_text:
        test_text = "#balas test"
        
    reply_match = re.match(r"(?i)^#balas(?:\s+|$)(.*)", test_text, re.DOTALL)
    
    msg = (
        f"Chat ID: {update.effective_chat.id}\n"
        f"Reply from Bot: {is_bot}\n"
        f"Matches: {matches}\n"
        f"Bot Text length: {len(bot_text)}\n"
        f"Regex Text: '{test_text}'\n"
        f"Regex Match: {bool(reply_match)}\n"
        f"Text Preview: {bot_text[:100]}"
    )
    await update.message.reply_text(msg)

async def debug_balas_interceptor(update, context):
    if not update.message:
        return
    text = update.message.text or update.message.caption or ""
    if text.strip().lower().startswith("#balas"):
        await update.message.reply_text(f"DEBUG INTERCEPTOR: Diterima! Text: {text[:20]}\nGroup: {update.effective_chat.id}")
