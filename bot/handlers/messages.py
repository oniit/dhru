from __future__ import annotations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes
import json
import asyncio
import time
import re
import html
import logging

log = logging.getLogger(__name__)

from bot.settings import (
    PROFILE_FIELDS,
    PETINGGI_GID,
    MABA_GROUP_NAMES,
    MABA_GROUP_GIDS,
    MABA_CH_IDS,
    is_admin_elevated,
)

from .common import (
    award_lengkapi_agra,
    build_maba_verification_text,
    can_approve_profile,
    can_report,
    field_label_for_key,
    get_active_charyarthi_divisions,
    missing_required_fields,
    profile_from_row,
    user_row,
    resolve_target_user,
    send_message_or_media_to_target,
    render_charyarthi_quiz_view,
)
from .kartu import STEP_KARTU_PHOTO, on_foto

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


def chunk_text_html(text: str, max_len: int = 3500) -> list[str]:
    """Split text into chunks such that html.escape(chunk) <= max_len.
    Preserves line breaks and does not split mid-character.
    """
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(html.escape(current + line)) <= max_len:
            current += line
        else:
            if current:
                chunks.append(current)
                current = ""
            if len(html.escape(line)) <= max_len:
                current = line
            else:
                for char in line:
                    if len(html.escape(current + char)) <= max_len:
                        current += char
                    else:
                        if current:
                            chunks.append(current)
                        current = char
    if current:
        chunks.append(current)
    return chunks


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
    
    if step == STEP_KARTU_PHOTO:
        await on_foto(update, context)
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
        if step in (STEP_KARTU_PHOTO, STEP_KONTRAK_TTD):
            await on_private_photo(update, context)
            return
            
    raw_text = update.message.text or update.message.caption or ""
    text = raw_text.strip()
    
    if not step:
        # Abaikan hanya /chat agar pesan owner tidak bocor ke grup petinggi
        if text.lower().startswith("/chat"):
            return

        is_trigger = False
        try:
            from .triggers import check_and_execute_trigger
            is_trigger = await check_and_execute_trigger(conn, update, context, text)
        except ImportError:
            pass
            
        if not is_trigger and PETINGGI_GID:
            try:
                u = update.effective_user
                first_name_esc = html.escape(u.first_name or "User")
                
                if u.username:
                    header = f"#ID_{uid} <a href='https://t.me/{u.username}'>{first_name_esc}</a>"
                else:
                    header = f"#ID_{uid} <a href='tg://user?id={uid}'>{first_name_esc}</a>"
                
                if update.message.text:
                    raw_text = update.message.text
                    raw_escaped = html.escape(raw_text)
                    single_msg = f"{header}:\n\n{raw_escaped}"
                    if len(single_msg) <= 3900:
                        await context.bot.send_message(
                            chat_id=PETINGGI_GID,
                            text=single_msg,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                    else:
                        chunks = chunk_text_html(raw_text, max_len=3500)
                        total_chunks = len(chunks)
                        if total_chunks > 0:
                            first_text = f"{header} (1/{total_chunks}):\n\n{html.escape(chunks[0])}"
                            first_msg = await context.bot.send_message(
                                chat_id=PETINGGI_GID,
                                text=first_text,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                            reply_id = getattr(first_msg, "message_id", None)
                            for idx, chunk in enumerate(chunks[1:], start=2):
                                cont_text = f"<i>[Lanjutan #ID_{uid} ({idx}/{total_chunks})]:</i>\n\n{html.escape(chunk)}"
                                await context.bot.send_message(
                                    chat_id=PETINGGI_GID,
                                    text=cont_text,
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                    reply_to_message_id=reply_id
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
                log.warning(f"Gagal meneruskan pesan ke PETINGGI_GID ({PETINGGI_GID}): {e}")
        return
        
    if step.startswith("REMPAH_SETOR:"):
        chat_id_str = step.split(":", 1)[1]
        try:
            deposit_val = int(text)
            if not (0 <= deposit_val <= 10):
                raise ValueError
        except ValueError:
            await update.message.reply_text("Harap masukkan angka antara 0 hingga 10:")
            return
            
        # Get active session for that chat
        chat_id = int(chat_id_str)
        session = await db.get_active_game_session(conn, chat_id)
        if not session or session["game_name"] != "kantong_rempah":
            await update.message.reply_text("Sesi game Kantong Rempah di grup tersebut sudah tidak aktif atau sudah selesai.")
            await db.set_onboarding_step(conn, uid, None)
            return            
        
        session_id = session["id"]
        lock = context.bot_data.setdefault("game_locks", {}).setdefault(session_id, asyncio.Lock())
        
        async with lock:
            current_session = await db.get_active_game_session(conn, chat_id)
            if not current_session or current_session["id"] != session_id:
                await update.message.reply_text("Sesi game Kantong Rempah di grup tersebut sudah tidak aktif.")
                await db.set_onboarding_step(conn, uid, None)
                return
                
            state = json.loads(current_session["state_json"])
            
            # Check phase
            if state.get("phase") != "deposit":
                await update.message.reply_text("Fase setoran untuk grup ini sudah ditutup!")
                await db.set_onboarding_step(conn, uid, None)
                return
                
            deposits = state.setdefault("deposits", {})
            deposits[str(uid)] = {
                "name": update.effective_user.first_name or update.effective_user.username or str(uid),
                "amount": deposit_val
            }
            
            await db.update_game_session_state(conn, session_id, state)
            
        await db.set_onboarding_step(conn, uid, None)
        await update.message.reply_text(f"✅ Berhasil menyetor <b>{deposit_val}</b> kantong rempah! Silakan kembali ke grup.", parse_mode="HTML")
        return

    if step == "MABA_NAME":
        name = text.title()
        profile_before = profile_from_row(row)
        await db.set_profile_partial(conn, uid, {"full_name": name})
        
        await award_lengkapi_agra(conn, db, uid, "full_name", profile_before, context, update.message.chat_id)
        
        await db.set_onboarding_step(conn, uid, "MABA_REASON")
        await update.message.reply_text(f"Terima kasih, {html.escape(name)}. Selanjutnya, ketikkan <b>Alasan Bergabung</b> Anda:", parse_mode="HTML")
        return
        
    if step == "MABA_REASON":
        reason = text
        await db.set_profile_partial(conn, uid, {"join_reason": reason})
        
        if MABA_CH_IDS:
            text_verify, _ = await build_maba_verification_text(context, uid)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Verifikasi Kembali", callback_data="maba:verify")]])
            await update.message.reply_text(text_verify, reply_markup=kb, parse_mode="HTML")
            await db.set_onboarding_step(conn, uid, "MABA_VERIFY_WAIT")
        else:
            # Skip checking if no channels defined
            await db.set_onboarding_step(conn, uid, "MABA_PROMO_WAIT")
            
            instruction_text = (
                "✅ Alasan diterima!\n\n"
                "<b>Langkah Terakhir:</b>\n"
                "Sebelum kamu mendapatkan link grup OSPEK, silakan lakukan minimal <b>1x promosi</b> (menyebar postingan OPSTUD ke minimal 1 LPM atau share di Telegram Story).\n\n"
                "Kirimkan buktinya ke sini dengan format:\n"
                "<code>/lpm &lt;link_pesan&gt;</code> atau <code>/story &lt;link_story&gt;</code>\n\n"
                "Jika sistem sudah membalas '<i>Link berhasil divalidasi</i>', klik tombol di bawah ini untuk mengambil link grup OSPEK-mu."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Ambil Link OSPEK", callback_data="maba:claim_ospek")]])
            await update.message.reply_text(instruction_text, reply_markup=kb, parse_mode="HTML")
            
        return

    if step == "CHARYARTHI_NAME":
        if not text:
            await update.message.reply_text("Nama tidak boleh kosong. Silakan ketikkan Nama Lengkap Anda:")
            return
        name = text[:100].strip().title()
        await db.set_profile_partial(conn, uid, {"full_name": name})
        await db.set_onboarding_step(conn, uid, "CHARYARTHI_REASON")
        
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="charyarthi:cancel")]])
        await update.message.reply_text(
            f"Terima kasih, <b>{html.escape(name)}</b>.\n\n"
            "Selanjutnya, silakan ketikkan <b>Alasan Anda Mendaftar Menjadi Staf</b>:",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        return

    if step == "CHARYARTHI_REASON":
        if not text:
            await update.message.reply_text("Alasan tidak boleh kosong. Silakan ketikkan alasan Anda mendaftar:")
            return
        reason = text[:3000].strip()
        await db.set_profile_partial(conn, uid, {"charyarthi_reason": reason})
        await db.set_onboarding_step(conn, uid, None)

        divisions = await get_active_charyarthi_divisions(db, conn)
        if not divisions:
            await update.message.reply_text("Maaf, saat ini belum ada divisi yang dibuka untuk pendaftaran.")
            return

        buttons = []
        row_btn = []
        for div_id, div_lbl in divisions:
            row_btn.append(InlineKeyboardButton(div_lbl, callback_data=f"charyarthi:div1:{div_id}"))
            if len(row_btn) == 2:
                buttons.append(row_btn)
                row_btn = []
        if row_btn:
            buttons.append(row_btn)
        buttons.append([InlineKeyboardButton("❌ Batal", callback_data="charyarthi:cancel")])

        user_r = await user_row(conn, db, uid)
        prof = profile_from_row(user_r) if user_r else {}
        name = prof.get("full_name", "Tanpa Nama")

        await update.message.reply_text(
            f"Alasan diterima.\n\n"
            "Silakan pilih <b>Divisi</b> yang ingin Anda lamar:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
        return

    if step.startswith("CHARYARTHI_ANS:"):
        parts = step.split(":", 2)
        if len(parts) == 3:
            if not text:
                await update.message.reply_text("Jawaban tidak boleh kosong. Silakan ketikkan jawaban Anda:")
                return
            div_id = parts[1]
            qid = int(parts[2])
            ans_clean = text[:4000].strip()
            await db.save_charyarthi_answer(conn, uid, div_id, qid, ans_clean)
            await db.set_onboarding_step(conn, uid, None)

            q = await db.get_charyarthi_question_by_id(conn, qid)
            q_order = q["question_order"] if q else ""
            await update.message.reply_text(f"✅ <i>Jawaban Soal {q_order} berhasil disimpan!</i>", parse_mode="HTML")
            dash_text, dash_kb = await render_charyarthi_quiz_view(uid, div_id, conn, db)
            await update.message.reply_text(dash_text, reply_markup=dash_kb, parse_mode="HTML")
        return

    if step.startswith("INPUT_SOAL_ADD:"):
        if not text:
            await update.message.reply_text("Teks soal tidak boleh kosong. Silakan ketikkan pertanyaan:")
            return
        div_id = step.split(":", 1)[1]
        await db.add_charyarthi_question(conn, div_id, text[:1000].strip())
        await db.set_onboarding_step(conn, uid, None)
        from bot.settings import get_division_label
        div_lbl = get_division_label(div_id)
        clean_alias = div_id[2:] if div_id.startswith("d_") else div_id
        await update.message.reply_text(
            f"✅ <b>Soal baru berhasil ditambahkan untuk divisi {html.escape(div_lbl)}!</b>\n\n"
            f"Ketik /soal {clean_alias} untuk melihat daftar soal lengkap.",
            parse_mode="HTML"
        )
        return

    if step == "INPUT_CODE":
        code = text.strip()
        cur = await conn.execute("SELECT * FROM access_codes WHERE code = ? AND used_by IS NULL", (code,))
        code_row = await cur.fetchone()
        if code_row:
            target_role = code_row["target_role"] if "target_role" in code_row.keys() else "student"
            
            if row["role"] == target_role:
                prof = profile_from_row(row)
                if target_role == "maba" and "maba_group" not in prof:
                    pass
                else:
                    await db.set_onboarding_step(conn, uid, None)
                    await update.message.reply_text(f"Gagal, ini adalah kode {target_role}, peranmu sebelumnya {row['role']}")
                    return
                
            await conn.execute("UPDATE access_codes SET used_by = ?, used_at = ? WHERE code = ?", (uid, time.time(), code))
            await db.set_role(conn, uid, target_role)
            await db.set_onboarding_step(conn, uid, None)
            await conn.commit()
            
            from bot.settings import OWNER_ID, BACKUP_CH_ID

            u = update.effective_user
            username_str = f"@{u.username}" if u.username else "Tanpa Username"
            name_str = u.first_name
            if u.last_name: name_str += f" {u.last_name}"

            if OWNER_ID and str(OWNER_ID) != "0":
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

            if target_role == "maba" and BACKUP_CH_ID:
                try:
                    await context.bot.send_message(
                        chat_id=BACKUP_CH_ID,
                        text=f"🔑 <b>Kode Akses Digunakan</b>\n"
                             f"<b>Oleh:</b> {name_str} ({username_str})\n"
                             f"<b>Kode:</b> <code>{code}</code>"
                    )
                except Exception:
                    pass
            
            if target_role == "internal":
                await update.message.reply_text("🔑 Kode akses internal valid! Peran Anda kini diubah menjadi Staf Internal.\nSilakan lengkapi profil Anda dengan mengetik /lengkapi.")
            elif target_role == "maba":
                # --- TIERED ROUND-ROBIN + BALANCER ---
                user_tier = await db.get_user_chat_tier(conn, uid)
                
                # Fetch all current mabas
                cur_mabas = await conn.execute("SELECT telegram_id, profile_json FROM users WHERE role = 'maba'")
                all_mabas = await cur_mabas.fetchall()
                
                tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
                total_counts = {1: 0, 2: 0, 3: 0, 4: 0}
                
                # Retrieve all tiers at once to be efficient
                all_tiers = await db.get_all_users_chat_tiers(conn)
                
                for r in all_mabas:
                    if str(r["telegram_id"]) == str(uid):
                        continue # Skip current user
                    prof = json.loads(r["profile_json"]) if r["profile_json"] else {}
                    mg = int(prof.get("maba_group", 0))
                    if 1 <= mg <= 4:
                        total_counts[mg] += 1
                        t = all_tiers.get(r["telegram_id"], "C")
                        if t == user_tier:
                            tier_counts[mg] += 1
                            
                # Priority 1: Distribute based on Tier
                min_tier_count = min(tier_counts.values())
                candidate_groups = [g for g, c in tier_counts.items() if c == min_tier_count]
                
                # Priority 2: Balancer (Pick the group with the lowest total members)
                if len(candidate_groups) == 1:
                    maba_group = candidate_groups[0]
                else:
                    min_total = min(total_counts[g] for g in candidate_groups)
                    best_groups = [g for g in candidate_groups if total_counts[g] == min_total]
                    maba_group = best_groups[0]
                
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
                            f"📣 <b>Alokasi Kelompok MABA</b>\n\n"
                            f"<b>Nama:</b> <a href=\"tg://user?id={uid}\">{name_str}</a>\n"
                            f"<b>Username:</b> {username_str}\n"
                            f"<b>Kelompok:</b> {MABA_GROUP_NAMES.get(maba_group, maba_group)}"
                        )
                        await context.bot.send_message(chat_id=KELOMPOK_GID, text=msg_kelompok, parse_mode="HTML")
                    except Exception as e:
                        log.warning(f"Gagal mengirim info kelompok ke {KELOMPOK_GID}: {e}")
                
                if _is_lengkapi_done(prof_u):
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
                        log.warning(f"Gagal membuat invite link Maba {uid}: {e}")
                        link = "(Gagal mendapatkan tautan grup. Pastikan bot adalah admin di grup kelompok.)"
                    await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi MABA (Kelompok {MABA_GROUP_NAMES.get(maba_group, maba_group)}).\n\nKarena data awal Anda sudah lengkap sebelumnya, silakan langsung bergabung ke grup kelompok Anda:\n{link}")
                else:
                    await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi MABA (Kelompok {MABA_GROUP_NAMES.get(maba_group, maba_group)}).\nSilakan ketik /lengkapi untuk mulai melengkapi data diri (Nama Lengkap).")
            else:
                await update.message.reply_text(f"Kode valid! Role Anda telah diperbarui menjadi {target_role}.\nSilakan ketik /lengkapi untuk mulai melengkapi data diri.")
        else:
            await update.message.reply_text("Kode tidak valid atau sudah digunakan. Silakan coba lagi, atau ketik /start untuk membatalkan.")
        return

    if step == STEP_KARTU_PHOTO:
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
                mg_str = new_profile.get("maba_group", "1")
                mg = int(mg_str) if str(mg_str).isdigit() else 1
                link = "(Link belum disetel oleh admin)"
                if len(MABA_GROUP_GIDS) >= mg:
                    gid = MABA_GROUP_GIDS[mg - 1]
                    try:
                        inv = await context.bot.create_chat_invite_link(gid, member_limit=1)
                        link = inv.invite_link
                    except Exception:
                        pass
                await update.message.reply_text(f"✨ Terima kasih. Data awal Anda sudah lengkap.\n\nAnda dimasukkan ke Kelompok {MABA_GROUP_NAMES.get(mg, mg)}. Silakan klik link berikut untuk bergabung ke grup kelompok Anda:\n{link}")
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
    try:
        now = time.time()
        cache = context.bot_data.setdefault("group_activity_cache", {})
        cache_key = (u.id, update.effective_chat.id)
        last_seen = cache.get(cache_key, 0)
        
        # Debounce seen_user and upsert_bot_chat to once per hour per user/group
        if now - last_seen > 3600:
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
            cache[cache_key] = now
            
        if not u.is_bot:
            await db.increment_message_count(
                conn=conn,
                user_id=u.id,
                chat_id=update.effective_chat.id
            )
    except Exception as e:
        log.error(f"Error in track_group_activity: {e}")

async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
        
    conn = _conn(context)
    raw_text = update.message.text or update.message.caption or ""
    text = raw_text.strip()
    
    if text.startswith("/"):
        return
        
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
        
    is_authorized = False
    if PETINGGI_GID and update.effective_chat.id == PETINGGI_GID:
        is_authorized = True
    elif is_admin_elevated(update.effective_user.id):
        is_authorized = True
        
    if not is_authorized:
        return
        
    reply_match = re.match(r"(?i)^#balas(?:\s+|$)(.*)", text, re.DOTALL)
    
    # If the admin didn't use #balas, we only care if they sent a sticker/video_note as a direct reply to the bot
    if not reply_match:
        reply = update.message.reply_to_message
        if reply and reply.from_user and reply.from_user.id == context.bot.id:
            bot_text = reply.text or reply.caption or ""
            matches = re.findall(r"#ID_(\d+)", bot_text)
            if matches and (update.message.sticker or update.message.video_note):
                target_id = int(matches[0])
                try:
                    await update.message.copy(chat_id=target_id)
                    await update.message.reply_text("✅ Media (Stiker/Video Note) berhasil dikirim ke user.")
                except Exception as e:
                    await update.message.reply_text(f"Gagal mengirim media: {e}")
        return

    # If they DID use #balas, validate everything and give errors if it fails
    reply = update.message.reply_to_message
    raw_balas = reply_match.group(1).strip()
    
    target_id = None
    target_desc = ""
    reply_text = raw_balas
    
    # 1. Cek jika mereply pesan bot yang memiliki #ID_...
    if reply and reply.from_user and reply.from_user.id == context.bot.id:
        bot_text = reply.text or reply.caption or ""
        matches = re.findall(r"#ID_(\d+)", bot_text)
        if matches:
            target_id = int(matches[0])
            target_desc = f"user #{target_id}"

    # 2. Cek jika target diberikan secara eksplisit: #balas @username <pesan> atau #balas <ID> <pesan>
    if not target_id and raw_balas:
        parts = raw_balas.split(maxsplit=1)
        potential_target = parts[0]
        if potential_target.startswith("@") or potential_target.isdigit():
            conn = _conn(context)
            db = _db(context)
            resolved_id, resolved_desc = await resolve_target_user(conn, db, potential_target)
            if resolved_id:
                target_id = resolved_id
                target_desc = resolved_desc
                reply_text = parts[1].strip() if len(parts) > 1 else ""

    if not target_id:
        if not reply:
            await update.message.reply_text(
                "⚠️ Anda harus me-reply pesan (yang diforward dari user) untuk menggunakan #balas,\n"
                "atau sertakan target: #balas @username <pesan> / #balas <ID> <pesan>"
            )
            return
            
        if not reply.from_user or reply.from_user.id != context.bot.id:
            await update.message.reply_text("⚠️ Anda harus me-reply pesan yang dikirim oleh bot ini.")
            return
            
        await update.message.reply_text("⚠️ Gagal: Tidak dapat menemukan #ID_ user pada pesan yang direply. Pastikan pesan tersebut memiliki format ID.")
        return
        
    has_media = bool(
        update.message.photo
        or update.message.video
        or update.message.document
        or update.message.audio
        or update.message.voice
        or update.message.animation
        or update.message.sticker
        or update.message.video_note
    )
    if not reply_text and not has_media:
        await update.message.reply_text("⚠️ Isi balasan tidak boleh kosong atau sertakan media. Gunakan format: #balas <pesan>")
        return
        
    try:
        await send_message_or_media_to_target(
            bot=context.bot,
            target_id=target_id,
            message=update.message,
            text_or_caption=reply_text,
            source_message=None,
        )
        await update.message.reply_text(f"✅ Balasan berhasil dikirim ke {target_desc or f'user #{target_id}'}.")
    except Exception as e:
        await update.message.reply_text(f"Gagal mengirim balasan: {e}")

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
        
    conn = _conn(context)
    db = _db(context)
    
    try:
        await db.sync_user_basic_info(
            conn,
            telegram_id=u.id,
            username=u.username,
            first_name=u.first_name,
            last_name=u.last_name
        )
        cache[u.id] = current_info
    except Exception as e:
        log.warning("Gagal sync user basic info (telegram_id=%s): %s", u.id, e)

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_member:
        return
        
    chat = update.chat_member.chat
    new_member = update.chat_member.new_chat_member
    old_member = update.chat_member.old_chat_member

    # Hanya jalankan jika user baru join (bukan leave, atau perubahan status lainnya)
    if (
        old_member.status in (ChatMember.LEFT, ChatMember.BANNED, ChatMember.RESTRICTED) 
        and new_member.status == ChatMember.MEMBER
    ) or (
        old_member.status == ChatMember.RESTRICTED
        and new_member.status == ChatMember.RESTRICTED 
        and new_member.is_member
        and not old_member.is_member
    ):
        conn = _conn(context)
        db = _db(context)
        
        chat_data = await db.get_bot_chat(conn, chat.id)
        if chat_data and chat_data["greeting_message"]:
            greeting = chat_data["greeting_message"]
            user = new_member.user
            
            # Replace placeholder if any
            first_name_esc = html.escape(user.first_name or "")
            greeting = greeting.replace("{name}", first_name_esc)
            if "{username}" in greeting:
                username_esc = f"@{html.escape(user.username)}" if user.username else first_name_esc
                greeting = greeting.replace("{username}", username_esc)
                
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=greeting,
                    parse_mode="HTML"
                )
            except Exception as e:
                log.error("Failed to send greeting message in chat %s: %s", chat.id, e)

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

