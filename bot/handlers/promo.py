import html
import logging
import random
import re
import string
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from bot.database import Database

log = logging.getLogger(__name__)

# Temporary in-memory store for OTPs
# Format: { "PROMO-XYZ": {"main_user_id": 12345, "expires_at": 1700000000} }
OTP_STORE: dict[str, dict] = {}

def generate_otp() -> str:
    return "KERJA-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def link_kerja_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Silakan gunakan perintah ini di chat pribadi (DM).")
        return

    main_user_id = update.effective_user.id
    
    # Cleanup expired OTPs (optional, but good practice)
    now = time.time()
    expired = [k for k, v in OTP_STORE.items() if v["expires_at"] < now]
    for k in expired:
        OTP_STORE.pop(k, None)

    code = generate_otp()
    OTP_STORE[code] = {
        "main_user_id": main_user_id,
        "expires_at": now + 600  # valid for 10 minutes
    }

    text = (
        "🔗 <b>Tautkan Akun Kerja</b>\n\n"
        "Untuk menautkan akun kerjamu (akun promosi), ikuti langkah ini:\n"
        "1. Start bot ini di akun kerjamu.\n"
        f"2. Kirimkan pesan berisi kode di bawah ini ke bot ini secara langsung (DM):\n\n"
        f"<code>{code}</code>\n\n"
        "<b>(Kode ini hanya berlaku selama 10 menit)</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cek_akun_kerja_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    main_user_id = update.effective_user.id
    
    linked_accounts = await db.get_linked_accounts(conn, main_user_id)
    if not linked_accounts:
        await update.message.reply_text("Kamu belum menautkan akun kerja apa pun. Gunakan /link_kerja untuk menautkan.")
        return

    text = "📋 <b>Daftar Akun Kerjamu yang Terdaftar:</b>\n\n"
    for idx, acc_id in enumerate(linked_accounts, start=1):
        text += f"{idx}. <code>{acc_id}</code>\n"
    text += "\nJika kamu menggunakan salah satu akun di atas untuk menyebar link promosi, saldo Agra akan tetap masuk ke akun utama ini."
    
    await update.message.reply_text(text, parse_mode="HTML")

async def _safe_edit_or_reply(msg, text: str, parse_mode: str = "HTML") -> None:
    try:
        await msg.edit_text(text, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception:
        try:
            await msg.reply_text(text, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception as e:
            log.warning("Gagal mengirim balasan edit/reply promo: %s", e)

def normalize_telegram_post_link(link: str) -> str | None:
    """
    Normalizes a Telegram post/message link to standard canonical format:
    https://t.me/<chat>/<msg_id>
    For private group links: https://t.me/c/<chat_id>/<msg_id>
    Returns None if format does not match.
    """
    if not link:
        return None
    raw = link.strip()
    m_priv = re.search(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/c/(\d+)/(\d+)", raw, re.IGNORECASE)
    if m_priv:
        return f"https://t.me/c/{m_priv.group(1)}/{m_priv.group(2)}"
    
    m_pub = re.search(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)/(\d+)", raw, re.IGNORECASE)
    if m_pub:
        username = m_pub.group(1).lower()
        if username not in ("c", "s", "joinchat", "share", "addstickers"):
            return f"https://t.me/{username}/{m_pub.group(2)}"

    return None

def normalize_telegram_story_link(link: str) -> str | None:
    """
    Normalizes a Telegram story link to standard canonical format:
    https://t.me/<username>/s/<story_id>
    """
    if not link:
        return None
    raw = link.strip()
    m_story = re.search(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)/s/(\d+)", raw, re.IGNORECASE)
    if m_story:
        return f"https://t.me/{m_story.group(1).lower()}/s/{m_story.group(2)}"
    return None

async def verify_lpm_link_embed(
    conn, db: Database, user_id: int, link: str, lpm_keyword: str
) -> tuple[bool, str, str | None]:
    """
    Validates a public LPM Telegram link by fetching its public embed (https://t.me/<chat>/<msg_id>?embed=1).
    Returns (is_valid, status_code, user_message).
    """
    import json
    match = re.search(r"t\.me/([^/]+)/(\d+)", link)
    if not match:
        return False, "INVALID_URL", (
            "Format tautan tidak dikenali.\n"
            "Pastikan tautan mengarah ke pesan spesifik, contoh:\n"
            "<code>https://t.me/grup_lpm/123</code>"
        )

    chat_username = match.group(1)
    msg_id = int(match.group(2))

    if chat_username.lower() == "c":
        return False, "PRIVATE_GROUP_NOT_SUPPORTED", (
            "Tautan dari grup Private tidak dapat dibaca oleh bot.\n"
            "Pastikan promosi dilakukan di Grup Publik (memiliki username grup)."
        )

    embed_url = f"https://t.me/{chat_username}/{msg_id}?embed=1"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(embed_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return False, "NOT_FOUND", (
                    "Pesan tidak ditemukan atau grup tersebut bersifat privat/dibatasi sehingga tidak dapat diakses oleh bot."
                )
            html_content = resp.text
    except Exception as e:
        log.warning("Gagal fetch embed %s: %s", embed_url, e)
        return False, "NETWORK_ERROR", None

    if "tgme_widget_message_error" in html_content or "Post not found" in html_content:
        return False, "NOT_FOUND", (
            "Pesan tidak ditemukan atau grup tersebut bersifat privat/dibatasi sehingga tidak dapat diakses oleh bot."
        )

    text_m = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html_content, re.DOTALL)
    raw_text = text_m.group(1) if text_m else ""
    msg_text = html.unescape(re.sub(r'<[^>]+>', '', raw_text)).strip()

    if not lpm_keyword or lpm_keyword.lower() not in msg_text.lower():
        return False, "NO_KEYWORD", (
            f"Teks pesan tidak memuat kata kunci promosi yang sesuai.\n"
            f"Wajib memuat kata kunci: <b>{html.escape(lpm_keyword)}</b>"
        )

    author_username = None
    author_name = ""
    author_link_m = re.search(r'class="tgme_widget_message_author_name[^"]*"[^>]*href="https?://t\.me/([^"/]+)"', html_content)
    if author_link_m:
        author_username = author_link_m.group(1).lower().lstrip("@")

    author_elem_m = re.search(r'<[a-zA-Z0-9]+ class="tgme_widget_message_author_name[^"]*"[^>]*>(.*?)</[a-zA-Z0-9]+>', html_content, re.DOTALL)
    if author_elem_m:
        raw_author_name = author_elem_m.group(1)
        author_name = html.unescape(re.sub(r'<[^>]+>', '', raw_author_name)).strip().lower()

    user_row = await db.get_user(conn, user_id)
    if not user_row:
        return False, "USER_NOT_FOUND", "Data pengguna tidak ditemukan di database bot."

    valid_usernames = set()
    valid_names = set()

    if user_row["username"]:
        valid_usernames.add(user_row["username"].lower().lstrip("@"))
    if user_row["first_name"]:
        valid_names.add(user_row["first_name"].lower().strip())

    prof = {}
    if user_row["profile_json"]:
        try:
            prof = json.loads(user_row["profile_json"] or "{}")
        except Exception:
            pass
    if prof.get("full_name"):
        valid_names.add(prof["full_name"].lower().strip())

    linked_ids = await db.get_linked_accounts(conn, user_id)
    for lid in linked_ids:
        l_row = await db.get_user(conn, lid)
        if l_row:
            if l_row["username"]:
                valid_usernames.add(l_row["username"].lower().lstrip("@"))
            if l_row["first_name"]:
                valid_names.add(l_row["first_name"].lower().strip())
            l_prof = {}
            if l_row["profile_json"]:
                try:
                    l_prof = json.loads(l_row["profile_json"] or "{}")
                except Exception:
                    pass
            if l_prof.get("full_name"):
                valid_names.add(l_prof["full_name"].lower().strip())

    is_sender_valid = False
    if author_username and author_username in valid_usernames:
        is_sender_valid = True
    elif author_name:
        for vn in valid_names:
            if vn and (vn == author_name or vn in author_name or author_name in vn):
                is_sender_valid = True
                break

    if not is_sender_valid:
        return False, "SENDER_MISMATCH", (
            "Pengirim pesan bukan akun utamamu dan bukan dari Akun Kerja yang sudah ditautkan.\n\n"
            "<i>💡 Catatan: Jika promosi dikirim menggunakan akun cadangan (clone/work account), "
            "tautkan akun tersebut terlebih dahulu menggunakan perintah <code>/link_kerja</code>.</i>"
        )

    return True, "VALID", None

async def lpm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Format Perintah Salah!</b>\n\n"
            "Gunakan format:\n"
            "<code>/lpm &lt;link_pesan&gt;</code>\n\n"
            "Contoh:\n"
            "<code>/lpm https://t.me/grup_lpm/123</code>",
            parse_mode="HTML"
        )
        return
        
    raw_link = context.args[0].strip()
    canonical_link = normalize_telegram_post_link(raw_link)
    if not canonical_link:
        if "/c/" in raw_link:
            await update.message.reply_text(
                "❌ <b>Grup Private Tidak Didukung</b>\n\n"
                "Tautan dari grup Private tidak dapat dibaca oleh bot.\n"
                "Pastikan promosi dilakukan di Grup Publik (memiliki username grup).",
                parse_mode="HTML"
            )
            return
        await update.message.reply_text(
            "❌ <b>Link Tidak Valid!</b>\n\n"
            "Format tautan tidak dikenali. Pastikan tautan diawali dengan <code>https://t.me/</code> "
            "dan mengarah ke pesan spesifik, contoh:\n"
            "<code>https://t.me/grup_lpm/123</code>",
            parse_mode="HTML"
        )
        return

    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    user_id = update.effective_user.id
    
    # Check if link exists in database
    rec = await db.get_promo_link_record(conn, canonical_link)
    if rec:
        if rec["status"] == "VALID":
            await update.message.reply_text("❌ Link promosi ini sudah pernah divalidasi dan diklaim sebelumnya.")
            return
        if rec["status"] in ("PENDING", "PROCESSING"):
            await update.message.reply_text(
                "⏳ <b>Link Sedang Diproses!</b>\n\n"
                "Link promosi ini sedang dalam antrean atau proses validasi. "
                "Mohon tunggu beberapa saat dan tidak mengirim ulang berkali-kali.",
                parse_mode="HTML"
            )
            return

    # Kirim balasan tunggu di awal agar pengguna langsung tahu bahwa bot merespons
    wait_msg = await update.message.reply_text(
        "⏳ <b>Sedang Memvalidasi Link LPM...</b>\n\n"
        "Sistem sedang memeriksa postingan promosi Anda ke server Telegram. Mohon tunggu sebentar...",
        parse_mode="HTML"
    )

    try:
        # Add to database with status PROCESSING so background jobs do NOT steal/duplicate it
        req_id = await db.add_promo_verification(conn, user_id, canonical_link, promo_type="lpm", status="PROCESSING")
        
        # Try immediate public embed verification
        lpm_keyword = await db.get_setting(conn, "promo_lpm_keyword", "dhruva")
        is_valid, status_code, err_msg = await verify_lpm_link_embed(conn, db, user_id, canonical_link, lpm_keyword)

        if is_valid:
            cur = await conn.execute(
                "UPDATE promo_verifications SET status = 'VALID' WHERE id = ? AND status = 'PROCESSING'",
                (req_id,)
            )
            if getattr(cur, "rowcount", 1) > 0:
                await db.add_agra(
                    conn,
                    target_id=user_id,
                    actor_id=user_id,
                    amount=1,
                    description="Reward promosi LPM",
                    chat_id=None,
                    message_id=None
                )
                await conn.commit()
                await _safe_edit_or_reply(
                    wait_msg,
                    f"✅ <b>Link LPM Berhasil Divalidasi!</b>\n\n"
                    f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
                    f"🎁 Kamu mendapatkan <b>+1 Agra</b>.",
                    parse_mode="HTML"
                )
            else:
                await _safe_edit_or_reply(
                    wait_msg,
                    f"ℹ️ <b>Link LPM Sudah Diproses</b>\n\n"
                    f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
                    f"Link promosi ini telah diverifikasi sebelumnya.",
                    parse_mode="HTML"
                )
        elif status_code not in ("NETWORK_ERROR", "PRIVATE_GROUP_NOT_SUPPORTED"):
            await conn.execute("UPDATE promo_verifications SET status = ? WHERE id = ?", (status_code, req_id))
            await conn.commit()
            await _safe_edit_or_reply(
                wait_msg,
                f"❌ <b>Gagal Memvalidasi Link LPM</b>\n\n"
                f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
                f"<b>Alasan:</b>\n{err_msg}",
                parse_mode="HTML"
            )
        elif status_code == "PRIVATE_GROUP_NOT_SUPPORTED":
            await conn.execute("UPDATE promo_verifications SET status = ? WHERE id = ?", (status_code, req_id))
            await conn.commit()
            await _safe_edit_or_reply(
                wait_msg,
                f"❌ <b>Grup Private Tidak Didukung</b>\n\n"
                f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
                f"{err_msg}",
                parse_mode="HTML"
            )
        else:
            # NETWORK_ERROR: set to PENDING so background queue can retry
            await conn.execute("UPDATE promo_verifications SET status = 'PENDING' WHERE id = ?", (req_id,))
            await conn.commit()
            await _safe_edit_or_reply(
                wait_msg,
                f"⏳ <b>Pemeriksaan Instan Tertunda</b>\n\n"
                f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
                f"Koneksi ke server Telegram sedang lambat. Link telah dicatat ke antrean validasi latar belakang.\n"
                f"Sistem akan memverifikasi otomatis dalam beberapa saat. Jika valid, saldo Agra akan otomatis bertambah.",
                parse_mode="HTML"
            )
    except Exception as e:
        log.exception("Error saat memproses validasi /lpm: %s", e)
        try:
            await conn.execute("UPDATE promo_verifications SET status = 'PENDING' WHERE link = ? AND status = 'PROCESSING'", (canonical_link,))
            await conn.commit()
        except Exception:
            pass
        await _safe_edit_or_reply(
            wait_msg,
            f"⚠️ <b>Terjadi Kendala Teknis Saat Memvalidasi</b>\n\n"
            f"🔗 <code>{html.escape(canonical_link)}</code>\n\n"
            f"<b>Detail Kendala:</b> <code>{html.escape(str(e))}</code>\n\n"
            f"Link kamu tetap tersimpan di sistem antrean dan akan diperiksa ulang secara otomatis.",
            parse_mode="HTML"
        )

async def handle_otp_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches OTP codes sent by promo accounts."""
    if not update.message or not update.message.text:
        return
        
    if update.effective_chat.type != "private":
        return

    text = update.message.text.strip().upper()
    if text.startswith("KERJA-") and len(text) == 12:
        now = time.time()
        otp_data = OTP_STORE.get(text)
        
        if not otp_data:
            await update.message.reply_text("❌ Kode OTP tidak valid atau salah ketik.")
            return
            
        if otp_data["expires_at"] < now:
            await update.message.reply_text("❌ Kode OTP sudah kedaluwarsa. Silakan minta ulang di akun utama.")
            OTP_STORE.pop(text, None)
            return
            
        main_user_id = otp_data["main_user_id"]
        promo_user_id = update.effective_user.id
        
        if main_user_id == promo_user_id:
            await update.message.reply_text("❌ Kamu mengirim kode dari akun utama yang sama. Harus dikirim dari akun kerja.")
            return

        db: Database = context.bot_data["db"]
        conn = context.bot_data["conn"]
        
        success = await db.add_linked_account(conn, main_user_id, promo_user_id)
        if success:
            await update.message.reply_text(
                "✅ <b>Berhasil!</b> Akun ini sekarang tertaut sebagai Akun Kerja.\n\n"
                "Mulai sekarang, semua link promosi yang dikirim oleh akun ini bisa diklaim menggunakan akun utama."
            )
            # Notifikasi ke akun utama
            try:
                await context.bot.send_message(
                    chat_id=main_user_id,
                    text=f"✅ Akun kerja dengan ID <code>{promo_user_id}</code> berhasil ditautkan ke akun utamamu!",
                    parse_mode="HTML"
                )
            except Exception as e:
                log.error(f"Gagal mengirim notif ke akun utama: {e}")
        else:
            await update.message.reply_text("❌ Akun ini sudah ditautkan ke akun utama tersebut sebelumnya.")
            
        OTP_STORE.pop(text, None)

async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.settings import OWNER_ID
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Khusus Owner.")
        return
    
    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    
    current_lpm = await db.get_setting(conn, "promo_lpm_keyword", "dhruva")
    current_story = await db.get_setting(conn, "promo_story_post", "(Belum diatur)")
    
    text = (
        "⚙️ *Menu Promo & Story Settings*\n\n"
        f"🔹 *Kata Kunci LPM Saat Ini:* `{current_lpm}`\n"
        f"🔹 *Link Post Story Saat Ini:* `{current_story}`\n\n"
        "Pilih tombol di bawah untuk mengubah pengaturannya:"
    )
    
    keyboard = [
        [InlineKeyboardButton("Set Syarat Kata LPM", callback_data="promo_set_lpm")],
        [InlineKeyboardButton("Set Link Post Story", callback_data="promo_set_story")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def promo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    from bot.settings import OWNER_ID
    if update.effective_user.id != OWNER_ID:
        await query.answer("Khusus Owner.", show_alert=True)
        return
        
    await query.answer()
    
    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    
    if query.data == "promo_set_lpm":
        await db.set_onboarding_step(conn, update.effective_user.id, "PROMO_WAIT_LPM")
        current_lpm = await db.get_setting(conn, "promo_lpm_keyword", "dhruva")
        text = (
            f"Kirimkan syarat kata untuk LPM.\n\n"
            f"💡 *Kata saat ini:* `{current_lpm}`\n\n"
            "_Kirim pesan berisi kata baru untuk mengubahnya, atau abaikan pesan ini jika tidak jadi mengubah._"
        )
        await query.edit_message_text(text, parse_mode="Markdown")
    elif query.data == "promo_set_story":
        await db.set_onboarding_step(conn, update.effective_user.id, "PROMO_WAIT_STORY")
        current_story = await db.get_setting(conn, "promo_story_post", "(Belum diatur)")
        text = (
            f"Kirimkan link post channel untuk validasi Story.\n\n"
            f"💡 *Link saat ini:* `{current_story}`\n\n"
            "_Kirim pesan berisi link baru (contoh: https://t.me/channel/123), atau abaikan jika tidak jadi mengubah._"
        )
        await query.edit_message_text(text, parse_mode="Markdown")

async def promo_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.settings import OWNER_ID
    if update.effective_user.id != OWNER_ID:
        return
        
    if not update.message or not update.message.text:
        return
        
    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    
    row = await db.get_user(conn, update.effective_user.id)
    if not row:
        return
        
    step = row["onboarding_step"]
    if step not in ("PROMO_WAIT_LPM", "PROMO_WAIT_STORY"):
        return
        
    text = update.message.text.strip()
    
    if step == "PROMO_WAIT_LPM":
        await db.set_setting(conn, "promo_lpm_keyword", text.lower())
        await update.message.reply_text(f"✅ Syarat kata LPM berhasil diubah menjadi: `{text.lower()}`", parse_mode="Markdown")
    elif step == "PROMO_WAIT_STORY":
        await db.set_setting(conn, "promo_story_post", text)
        await update.message.reply_text(f"✅ Link post Story berhasil diubah menjadi:\n{text}")
        
    await db.set_onboarding_step(conn, update.effective_user.id, None)

async def story_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Format salah! Gunakan: `/story <link_story>`\nContoh: `/story https://t.me/username/s/15`", parse_mode="Markdown")
        return
        
    raw_link = context.args[0].strip()
    canonical_link = normalize_telegram_story_link(raw_link)
    if not canonical_link:
        await update.message.reply_text("Link tidak valid. Pastikan formatnya benar (contoh: https://t.me/username/s/15).")
        return

    db: Database = context.bot_data["db"]
    conn = context.bot_data["conn"]
    user_id = update.effective_user.id
    
    record = await db.get_promo_link_record(conn, canonical_link)
    if record:
        if record["status"] == "VALID":
            await update.message.reply_text("❌ Link ini sudah pernah diklaim sebelumnya.")
            return
        if record["status"] in ("PENDING", "PROCESSING"):
            await update.message.reply_text("⏳ Link ini sedang dalam antrean atau proses validasi. Mohon tunggu beberapa saat.")
            return

    await db.add_promo_verification(conn, user_id, canonical_link, promo_type="story", status="PENDING")
    
    await update.message.reply_text(
        "⏳ Link Story berhasil disubmit! Sistem sedang memvalidasi story-mu. "
        "Pastikan akunmu publik agar bot bisa mengeceknya."
    )

def setup_promo_handlers(application) -> None:
    application.add_handler(CommandHandler("link_kerja", link_kerja_cmd))
    application.add_handler(CommandHandler("cek_akun_kerja", cek_akun_kerja_cmd))
    application.add_handler(CommandHandler("lpm", lpm_cmd))
    application.add_handler(CommandHandler("story", story_cmd))
    application.add_handler(CommandHandler("promo", promo_cmd))
    application.add_handler(CallbackQueryHandler(promo_callback, pattern="^promo_set_"))
    
    # Filter only text messages that start with KERJA-
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r"(?i)^KERJA-[A-Z0-9]{6}$"), handle_otp_message),
        group=1
    )
    
    # Text input handler for promo settings (runs in separate group so it doesn't block commands)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, promo_text_handler),
        group=2
    )
