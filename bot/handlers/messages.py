from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
import time
import re

from bot.settings import PROFILE_FIELDS, PETINGGI_GID

from .common import (
    can_report,
    field_label_for_key,
    missing_required_fields,
    profile_from_row,
    user_row,
)
from .ktm import STEP_KTM_PHOTO, on_ktm_photo
from .karpeg import STEP_KARPEG_PHOTO, on_karpeg_photo

ADMIN_PROFILE_TARGET_UD = "admin_profile_target"
LENGKAPI_DONE_KEY = "__lengkapi_done"


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _is_lengkapi_done(profile: dict) -> bool:
    return bool(profile.get(LENGKAPI_DONE_KEY))


async def _mark_lengkapi_done_if_complete(conn, db, telegram_id: int) -> None:
    row = await user_row(conn, db, telegram_id)
    if not row:
        return
    profile = profile_from_row(row)
    if _is_lengkapi_done(profile):
        return
    if not missing_required_fields(profile, row["role"]):
        await db.set_profile_partial(conn, telegram_id, {LENGKAPI_DONE_KEY: True})


async def on_private_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.photo:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    step = row["onboarding_step"] or ""
    
    from .kontrak import STEP_KONTRAK_TTD, on_kontrak_ttd
    
    if step == STEP_KTM_PHOTO:
        await on_ktm_photo(update, context)
    elif step == STEP_KARPEG_PHOTO:
        await on_karpeg_photo(update, context)
    elif step == STEP_KONTRAK_TTD:
        await on_kontrak_ttd(update, context)

async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    step = row["onboarding_step"] or ""
    
    if update.message.photo and step:
        from .kontrak import STEP_KONTRAK_TTD
        if step in (STEP_KTM_PHOTO, STEP_KARPEG_PHOTO, STEP_KONTRAK_TTD):
            await on_private_photo(update, context)
            return
            
    raw_text = update.message.text or update.message.caption or ""
    text = raw_text.strip()
    
    if not step:
        is_trigger = False
        try:
            from .triggers import check_and_execute_trigger
            is_trigger = await check_and_execute_trigger(conn, update, context, text)
        except ImportError:
            pass
            
        if not is_trigger and PETINGGI_GID:
            try:
                import html
                u = update.effective_user
                first_name_esc = html.escape(u.first_name or "User")
                
                if u.username:
                    header = f"#ID_{uid} <a href='https://t.me/{u.username}'>{first_name_esc}</a>"
                else:
                    header = f"#ID_{uid} <a href='tg://user?id={uid}'>{first_name_esc}</a>"
                
                if update.message.text:
                    text_esc = html.escape(update.message.text)
                    await context.bot.send_message(
                        chat_id=PETINGGI_GID,
                        text=f"{header}:\n\n{text_esc}",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                elif update.message.sticker or update.message.video_note:
                    copied_msg = await update.message.copy(chat_id=PETINGGI_GID)
                    await context.bot.send_message(
                        chat_id=PETINGGI_GID,
                        text=header,
                        parse_mode="HTML",
                        reply_to_message_id=copied_msg.message_id
                    )
                else:
                    original_caption = update.message.caption or ""
                    # Telegram max caption is 1024 chars. Our header takes ~130 chars.
                    if len(original_caption) > 850:
                        copied_msg = await update.message.copy(chat_id=PETINGGI_GID)
                        await context.bot.send_message(
                            chat_id=PETINGGI_GID,
                            text=header,
                            parse_mode="HTML",
                            reply_to_message_id=copied_msg.message_id
                        )
                    else:
                        new_caption = f"{header}\n{html.escape(original_caption)}"
                        await update.message.copy(
                            chat_id=PETINGGI_GID,
                            caption=new_caption,
                            parse_mode="HTML"
                        )
                    
                if row["role"] == "public":
                    await update.message.reply_text("Pesan Anda telah diteruskan ke tim kami.")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Gagal meneruskan pesan ke PETINGGI_GID ({PETINGGI_GID}): {e}")
        return
        
    if step == "MABA_NAME":
        name = text.title()
        profile_before = profile_from_row(row)
        await db.set_profile_partial(conn, uid, {"full_name": name})
        
        from bot.handlers.common import award_lengkapi_agra
        await award_lengkapi_agra(conn, db, uid, "full_name", profile_before, context, update.message.chat_id)
        
        await db.set_onboarding_step(conn, uid, "MABA_REASON")
        await update.message.reply_text(f"Terima kasih, {name}. Selanjutnya, ketikkan **Alasan Bergabung** Anda:", parse_mode="Markdown")
        return
        
    if step == "MABA_REASON":
        reason = text
        await db.set_profile_partial(conn, uid, {"join_reason": reason})
        
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from bot.settings import MABA_CH_IDS
        from bot.handlers.common import build_maba_verification_text
        
        if MABA_CH_IDS:
            text_verify, _ = await build_maba_verification_text(context, uid)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Verifikasi Kembali", callback_data="maba:verify")]])
            await update.message.reply_text(text_verify, reply_markup=kb, parse_mode="Markdown")
        else:
            # Skip checking if no channels defined
            from bot.database import ROLE_MABA
            from bot.settings import MABA_GROUP_LINK
            await db.update_user_role(conn, uid, ROLE_MABA)
            
            success_text = "✅ Berhasil! Anda telah terdaftar sebagai Mahasiswa Baru.\n\n"
            if MABA_GROUP_LINK:
                success_text += f"Silakan bergabung ke grup OSPEK melalui link berikut:\n{MABA_GROUP_LINK}\n\nDi dalam grup, Anda akan mendapatkan informasi seputar kode akademik."
            else:
                success_text += "Grup OSPEK belum diatur oleh admin. Silakan tunggu informasi selanjutnya."
            
            await update.message.reply_text(success_text, disable_web_page_preview=True)
            
            from bot.settings import PENDAFTAR_CH_ID
            if PENDAFTAR_CH_ID:
                try:
                    row_tmp = await user_row(conn, db, uid)
                    prof_tmp = profile_from_row(row_tmp)
                    name_tmp = prof_tmp.get("full_name", "Tanpa Nama")
                    username_tmp = f"@{row_tmp['username']}" if row_tmp and row_tmp["username"] else "-"
                    msg_pendaftar = f"**Nama:** [{name_tmp}](tg://user?id={uid})\n**Username:** {username_tmp}\n**Alasan Bergabung:** {reason}\n**ID:** `{uid}`"
                    await context.bot.send_message(chat_id=PENDAFTAR_CH_ID, text=msg_pendaftar, parse_mode="Markdown")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Gagal mengirim info pendaftar ke {PENDAFTAR_CH_ID}: {e}")
            
        await db.set_onboarding_step(conn, uid, None)
        return

    if step == "INPUT_CODE":
        code = text.strip()
        cur = await conn.execute("SELECT * FROM access_codes WHERE code = ? AND used_by IS NULL", (code,))
        code_row = await cur.fetchone()
        if code_row:
            target_role = code_row["target_role"] if "target_role" in code_row.keys() else "student"
            await conn.execute("UPDATE access_codes SET used_by = ?, used_at = ? WHERE code = ?", (uid, time.time(), code))
            await db.set_role(conn, uid, target_role)
            await db.set_onboarding_step(conn, uid, None)
            await conn.commit()
            
            from bot.settings import OWNER_ID
            if OWNER_ID and str(OWNER_ID) != "0":
                u = update.effective_user
                username_str = f"@{u.username}" if u.username else "Tanpa Username"
                name_str = u.first_name
                if u.last_name: name_str += f" {u.last_name}"
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"🔑 <b>Kode Akses Digunakan</b>\n"
                             f"<b>Oleh:</b> {name_str} ({username_str})\n"
                             f"<b>ID:</b> <code>{u.id}</code>\n"
                             f"<b>Role:</b> <code>{target_role}</code>\n"
                             f"<b>Kode:</b> <code>{code}</code>"
                    )
                except Exception:
                    pass
            
            if target_role == "internal":
                await update.message.reply_text("🔑 Kode akses internal valid! Peran Anda kini diubah menjadi Staf Internal.\nSilakan lengkapi profil Anda dengan mengetik /lengkapi.")
            elif target_role == "maba":
                cur_maba = await conn.execute(
                    "SELECT COUNT(*) as c FROM access_codes WHERE target_role = 'maba' AND used_by IS NOT NULL AND (used_at < (SELECT used_at FROM access_codes WHERE code = ?) OR (used_at = (SELECT used_at FROM access_codes WHERE code = ?) AND code <= ?))",
                    (code, code, code)
                )
                maba_order_row = await cur_maba.fetchone()
                m_order = int(maba_order_row["c"]) if maba_order_row else 1
                maba_group = ((m_order - 1) % 4) + 1
                await db.set_profile_partial(conn, uid, {"maba_group": maba_group})
                
                await _mark_lengkapi_done_if_complete(conn, db, uid)
                row_u = await user_row(conn, db, uid)
                prof_u = profile_from_row(row_u) if row_u else {}
                
                from bot.settings import KELOMPOK_GID
                if KELOMPOK_GID:
                    try:
                        name_str = prof_u.get("full_name", "Tanpa Nama")
                        username_str = f"@{row_u['username']}" if row_u and row_u.get("username") else "-"
                        msg_kelompok = (
                            f"📣 **Alokasi Kelompok MABA**\n\n"
                            f"**Nama:** [{name_str}](tg://user?id={uid})\n"
                            f"**Username:** {username_str}\n"
                            f"**Kelompok:** {maba_group}"
                        )
                        await context.bot.send_message(chat_id=KELOMPOK_GID, text=msg_kelompok, parse_mode="Markdown")
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Gagal mengirim info kelompok ke {KELOMPOK_GID}: {e}")
                
                if _is_lengkapi_done(prof_u):
                    from bot.settings import MABA_GROUP_GIDS
                    link = "(Grup kelompok belum disetel oleh admin)"
                    try:
                        if len(MABA_GROUP_GIDS) >= maba_group:
                            gid = MABA_GROUP_GIDS[maba_group - 1]
                            invite = await context.bot.create_chat_invite_link(
                                chat_id=gid, 
                                member_limit=1, 
                                name=f"Maba {uid}"
                            )
                            link = invite.invite_link
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Gagal membuat invite link Maba {uid}: {e}")
                        link = "(Gagal mendapatkan tautan grup. Pastikan bot adalah admin di grup kelompok.)"
                    await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi MABA (Kelompok {maba_group}).\n\nKarena data awal Anda sudah lengkap sebelumnya, silakan langsung bergabung ke grup kelompok Anda:\n{link}")
                else:
                    await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi MABA (Kelompok {maba_group}).\nSilakan ketik /lengkapi untuk mulai melengkapi data diri (Nama Lengkap).")
            else:
                await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi {target_role}.\nSilakan ketik /lengkapi untuk mulai melengkapi data diri.")
        else:
            await update.message.reply_text("Kode tidak valid atau sudah digunakan. Silakan coba lagi, atau ketik /start untuk membatalkan.")
        return

    if step == STEP_KTM_PHOTO:
        await update.message.reply_text(
            "Sekarang bot menunggu <b>foto</b> (bukan teks). Kirim satu foto wajah di chat ini.\n"
            "Atau ketik /start untuk membatalkan."
        )
        return

    if step.startswith("TUGAS_JUDUL:"):
        from .tugas import handle_tugas_judul
        await handle_tugas_judul(update, context, step.split(":", 1)[1])
        return

    if step.startswith("TUGAS_INPUT:"):
        from .tugas import handle_tugas_input
        await handle_tugas_input(update, context, int(step.split(":", 1)[1]))
        return

    if step.startswith("TUGAS_TOLAK:"):
        from .tugas import handle_tugas_tolak
        await handle_tugas_tolak(update, context, int(step.split(":", 1)[1]))
        return
    if step.startswith("ADMIN_TEXT_LC:") or step.startswith("TEXT_LC:") or step.startswith("TEXT_EC:"):
        field_key = step.split(":", 1)[1]
        
        if field_key == "full_name":
            text = text.title()
        elif field_key == "muse":
            text = text.upper()
            
        if field_key == "birth_date":
            if not re.match(r"^\d{6}$", text):
                await update.message.reply_text("Format tanggal lahir harus ddmmyy (contoh: 311299). Silakan ulangi:")
                return
            try:
                from datetime import datetime
                datetime.strptime(text, "%d%m%y")
            except ValueError:
                await update.message.reply_text("Tanggal lahir tidak valid. Pastikan tanggal ada di kalender (contoh: 311299). Silakan ulangi:")
                return

    if step.startswith("ADMIN_TEXT_LC:"):
        field_key = step.split(":", 1)[1]
        target_tid = context.user_data.get(ADMIN_PROFILE_TARGET_UD)
        row_actor = await user_row(conn, db, uid)
        if not target_tid or not row_actor or not can_approve_profile(row_actor["role"], profile_from_row(row_actor)):
            await db.set_onboarding_step(conn, uid, None)
            return
        await db.set_profile_partial(conn, target_tid, {field_key: text})
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(
            conn,
            uid,
            "admin_profile_set",
            f"target={target_tid} key={field_key}",
        )
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        await update.message.reply_text(
            f"✅ {lab} untuk <code>{target_tid}</code> disimpan."
        )
        return

    if step.startswith("TEXT_LC:"):
        field_key = step.split(":", 1)[1]
        profile = profile_from_row(row)
        if _is_lengkapi_done(profile):
            await db.set_onboarding_step(conn, uid, None)
            await update.message.reply_text("/lengkapi sudah ditutup. Gunakan /ubah.")
            return
        await db.set_profile_partial(conn, uid, {field_key: text})
        await _mark_lengkapi_done_if_complete(conn, db, uid)
        
        from .common import award_lengkapi_agra
        await award_lengkapi_agra(conn, db, uid, field_key, profile, context, update.message.chat_id)
        
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        
        new_row = await user_row(conn, db, uid)
        new_profile = profile_from_row(new_row)
        if _is_lengkapi_done(new_profile) and not _is_lengkapi_done(profile):
            if new_row["role"] == "internal":
                await update.message.reply_text("✨ Terima kasih. Data awal Anda sudah lengkap. Anda kini dapat mulai beraktivitas, silakan ketik /kontrak untuk membuat ID Card Pegawai Anda.")
            elif new_row["role"] == "maba":
                from bot.settings import MABA_GROUP_LINKS
                mg = int(new_profile.get("maba_group", 1))
                link = MABA_GROUP_LINKS[mg - 1]
                if not link:
                    link = "(Link belum disetel oleh admin)"
                await update.message.reply_text(f"✨ Terima kasih. Data awal Anda sudah lengkap.\n\nAnda dimasukkan ke Kelompok {mg}. Silakan klik link berikut untuk bergabung ke grup kelompok Anda:\n{link}")
            else:
                await update.message.reply_text("✨ Terima kasih. Data awal Anda sudah lengkap. Anda kini dapat menggunakan seluruh fitur sesuai role Anda.")
        else:
            await update.message.reply_text(f"✅ {lab} disimpan.")
        return

    if step.startswith("TEXT_EC:"):
        field_key = step.split(":", 1)[1]
        profile = profile_from_row(row)
        if profile.get(field_key) == text:
            await update.message.reply_text("Tidak ada perubahan yang diajukan.")
            await db.set_onboarding_step(conn, uid, None)
            return

        if row["role"] in ("owner", "admin"):
            await db.set_profile_partial(conn, uid, {field_key: text})
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(conn, uid, "profile_direct_update", field_key)
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            lab = fdef.label if fdef else field_label_for_key(field_key)
            await update.message.reply_text(f"✅ {lab} disimpan (auto-approved).")
            return
            
        rid = await db.add_profile_request(conn, uid, {field_key: text})
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await update.message.reply_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin."
        )
        from .commands import _notify_moderators_profile

        await _notify_moderators_profile(
            context, db, conn, rid, uid, {field_key: text}
        )
        return


async def track_group_activity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    conn = _conn(context)
    db = _db(context)
    u = update.effective_user
    await db.touch_group_seen_user(
        conn,
        chat_id=update.effective_chat.id,
        telegram_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name,
        is_bot=u.is_bot,
    )
    await db.upsert_bot_chat(
        conn=conn,
        chat_id=update.effective_chat.id,
        chat_type=update.effective_chat.type,
        title=update.effective_chat.title or "Tanpa Nama",
        is_active=True
    )

async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
        
    conn = _conn(context)
    raw_text = update.message.text or update.message.caption or ""
    text = raw_text.strip()
    
    try:
        from .triggers import check_and_execute_trigger
        is_trigger = await check_and_execute_trigger(conn, update, context, text)
        if is_trigger:
            return
    except ImportError:
        pass
        
    try:
        from .games import process_game_message
        is_game_handled = await process_game_message(conn, _db(context), update, context)
        if is_game_handled:
            return
    except ImportError:
        pass
        
    if not PETINGGI_GID or update.effective_chat.id != PETINGGI_GID:
        return
        
    reply = update.message.reply_to_message
    if reply and reply.from_user and reply.from_user.id == context.bot.id:
        bot_text = reply.text or reply.caption or ""
        matches = re.findall(r"#ID_(\d+)", bot_text)
        if matches:
            target_id = int(matches[0]) # Use the FIRST match since we put the header at the top
            
            # Stickers and Video Notes cannot have captions, so they cannot contain #balas. 
            # We must forward them directly.
            if update.message.sticker or update.message.video_note:
                try:
                    await update.message.copy(chat_id=target_id)
                    await update.message.reply_text("✅ Media (Stiker/Video Note) berhasil dikirim ke user.")
                except Exception as e:
                    await update.message.reply_text(f"Gagal mengirim media: {e}")
                return
                
            reply_match = re.match(r"(?i)^#balas(?:\s+|$)(.*)", text, re.DOTALL)
            if reply_match:
                reply_text = reply_match.group(1).strip()
                if not reply_text and update.message.text:
                    await update.message.reply_text("⚠️ Isi balasan tidak boleh kosong atau sertakan media. Gunakan format: #balas <pesan>")
                    return
                    
                try:
                    if update.message.text:
                        # Use parse_mode=None to prevent HTML parsing crashes if admin types < or >
                        await context.bot.send_message(chat_id=target_id, text=reply_text, parse_mode=None)
                    else:
                        await update.message.copy(
                            chat_id=target_id,
                            caption=reply_text,
                            parse_mode=None
                        )
                    await update.message.reply_text("✅ Balasan berhasil dikirim ke user.")
                except Exception as e:
                    await update.message.reply_text(f"Gagal mengirim balasan: {e}")

from telegram import ChatMember
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.my_chat_member:
        return
    
    conn = _conn(context)
    db = _db(context)
    
    chat = update.my_chat_member.chat
    new_status = update.my_chat_member.new_chat_member.status
    
    is_active = new_status in (
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
        ChatMember.RESTRICTED,
    )
    
    await db.upsert_bot_chat(
        conn=conn,
        chat_id=chat.id,
        chat_type=chat.type,
        title=chat.title or "Tanpa Nama",
        is_active=is_active
    )

async def global_profile_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    u = update.effective_user
    if u.is_bot:
        return
        
    # In-memory cache layer to prevent spamming DB queries
    cache = context.bot_data.setdefault("profile_cache", {})
    current_info = (u.username, u.first_name, u.last_name)
    
    if cache.get(u.id) == current_info:
        return  # No changes detected, skip hitting the database entirely
        
    cache[u.id] = current_info
        
    conn = _conn(context)
    db = _db(context)
    
    await db.sync_user_basic_info(
        conn,
        telegram_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name
    )

async def on_chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_join_request:
        return
    uid = update.chat_join_request.from_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if row and row['role'] == 'maba':
        await update.chat_join_request.approve()
    else:
        pass  # ignore or you could .decline()

