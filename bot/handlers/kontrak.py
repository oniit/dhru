"""Perintah /kontrak — manajemen kontrak internal."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import ROLE_ADMIN, ROLE_INTERNAL, ROLE_OWNER
from bot.kontrak_card import render_kontrak_png_bytes
from bot.settings import OWNER_ID, multi_choice_labels

from .common import profile_from_row, user_row

log = logging.getLogger(__name__)

STEP_KONTRAK_TTD = "KONTRAK_TTD"

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", 
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]
ROMAN_MONTHS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _private_only_reply(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


async def _download_telegram_photo(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes | None:
    try:
        tg_file = await context.bot.get_file(file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        log.warning("Unduh foto TTD gagal file_id=%s", file_id[:20], exc_info=True)
        return None


def calculate_contract_period(start_timestamp: float, is_new_or_renew: bool = True) -> tuple[str, str, float]:
    """Mengembalikan rentang tanggal kontrak (start_str, end_str, end_ts).
    Start: Hari ini. End: Tanggal 17 Bulan Genap Terdekat di masa depan.
    Jika is_new_or_renew=True dan tanggal berada di bulan genap dengan tanggal >= 10 (H-7 sebelum tgl 17),
    maka masa akhir kontrak otomatis dilompati ke tanggal 17 bulan genap berikutnya (+2 bulan).
    """
    dt_start = datetime.fromtimestamp(start_timestamp)
    start_str = f"{dt_start.day} {MONTH_NAMES[dt_start.month - 1]} {dt_start.year}"

    y = dt_start.year
    m = dt_start.month
    d = dt_start.day

    if is_new_or_renew:
        if m % 2 != 0:
            end_m = m + 1
            if end_m > 12:
                end_m = 2
                y += 1
        else:
            if d < 10:
                end_m = m
            else:
                end_m = m + 2
                if end_m > 12:
                    end_m = 2
                    y += 1
    else:
        # Pengecekan periode kalender umum (bukan penandatanganan baru)
        if m % 2 != 0:
            end_m = m + 1
            if end_m > 12:
                end_m = 2
                y += 1
        else:
            if d < 17:
                end_m = m
            else:
                end_m = m + 2
                if end_m > 12:
                    end_m = 2
                    y += 1

    end_str = f"17 {MONTH_NAMES[end_m - 1]} {y}"
    dt_end = datetime(y, end_m, 17, 23, 59, 59)
    end_ts = dt_end.timestamp()

    return start_str, end_str, end_ts


def _get_contract_status(profile: dict, now_ts: float) -> dict:
    c_end_ts = profile.get("contract_end_ts")
    c_seq = profile.get("contract_seq_no")
    has_ttd = bool((profile.get("ttd_file_id") or "").strip())

    if not c_end_ts or not c_seq:
        return {
            "has_contract": False,
            "has_ttd": has_ttd,
            "is_active": False,
            "is_expiring": False,
            "is_expired": False,
            "status_icon": "🔄" if has_ttd else "❌",
            "status_label": "Menunggu Pengesahan" if has_ttd else "Belum Kontrak",
        }

    end_f = float(c_end_ts)
    is_expired = now_ts > end_f
    is_expiring = not is_expired and (end_f - now_ts) < (7 * 24 * 3600)
    is_active = not is_expired and not is_expiring

    if is_active:
        icon = "✅"
        label = "Aktif"
    elif is_expiring:
        icon = "⚠️"
        label = "Akan Berakhir (H-7)"
    else:
        icon = "❌"
        label = "Kadaluarsa"

    return {
        "has_contract": True,
        "has_ttd": has_ttd,
        "is_active": is_active,
        "is_expiring": is_expiring,
        "is_expired": is_expired,
        "status_icon": icon,
        "status_label": label,
    }


async def cmd_kontrak_ttd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text("/kontrak ttd hanya di chat privat dengan bot.")
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Hanya staf/internal yang bisa mengisi tanda tangan kontrak.")
        return

    await db.set_onboarding_step(conn, uid, STEP_KONTRAK_TTD)
    await update.message.reply_text(
        "✍️ <b>Pengisian Tanda Tangan</b>\n\n"
        "Silakan kirim tanda tangan digital Anda dalam bentuk foto (bukan file).\n\n"
        "<b>Tanda tangan harus berwarna hitam dengan background putih.</b>",
        parse_mode="HTML"
    )


async def on_kontrak_ttd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.photo:
        return
    if not _private_only_reply(update):
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    step = (row["onboarding_step"] or "").strip()
    if step != STEP_KONTRAK_TTD:
        return
    if row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await db.set_onboarding_step(conn, uid, None)
        return

    photos = update.message.photo
    largest = photos[-1]
    file_id = largest.file_id

    await db.set_profile_partial(conn, uid, {"ttd_file_id": file_id})
    await db.set_onboarding_step(conn, uid, None)

    profile = profile_from_row(row)
    profile["ttd_file_id"] = file_id
    now_ts = time.time()
    st = _get_contract_status(profile, now_ts)

    if st["is_active"]:
        c_start = profile.get("contract_start") or "—"
        c_end = profile.get("contract_end") or "—"
        await update.message.reply_text(
            "✅ <b>Tanda tangan berhasil diperbarui!</b>\n\n"
            f"Tanda tangan baru Anda telah tersimpan dan diperbarui di sistem.\n"
            f"Karena kontrak kerja Anda untuk periode <b>{c_start} s/d {c_end}</b> sedang aktif berjalan, "
            "perubahan tanda tangan ini tidak mengubah masa berlaku maupun status kontrak Anda.\n\n"
            "Ketik <code>/kontrak saya</code> untuk melihat kontrak Anda dengan tanda tangan terbaru.",
            parse_mode="HTML"
        )
    elif st["is_expiring"] or st["is_expired"]:
        await update.message.reply_text(
            "✅ <b>Tanda tangan berhasil diperbarui!</b>\n\n"
            "Tanda tangan baru Anda telah tersimpan. Masa kontrak Anda saat ini telah atau akan segera berakhir.\n"
            "Silakan ketik <code>/kontrak renew</code> untuk memperbarui masa kontrak ke periode berikutnya dengan tanda tangan baru ini.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "✅ <b>Tanda tangan berhasil disimpan!</b>\n\n"
            "Silakan ketik <code>/kontrak saya</code> untuk meninjau draf dan mengesahkan kontrak kerja Anda.",
            parse_mode="HTML"
        )


async def _render_kontrak_png(
    context: ContextTypes.DEFAULT_TYPE,
    row: dict,
    profile: dict,
    start_str: str,
    end_str: str,
    nomor_surat: str,
    ttd_bytes: bytes | None,
) -> bytes | None:
    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"
    target_username = row["username"]
    username_str = f"@{target_username}" if target_username else "—"

    try:
        return render_kontrak_png_bytes(
            name=name,
            role_detail=role_detail,
            username=username_str,
            start_date_str=start_str,
            end_date_str=end_str,
            ttd_bytes=ttd_bytes,
            nomor_surat=nomor_surat,
        )
    except Exception as e:
        log.exception("render kontrak gagal uid=%s: %s", row.get("telegram_id"), e)
        return None


async def _send_active_kontrak(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    row: dict,
    profile: dict,
) -> None:
    fid = (profile.get("ttd_file_id") or "").strip()
    photo_bytes = await _download_telegram_photo(context, fid) if fid else None

    start_str = profile.get("contract_start") or "—"
    end_str = profile.get("contract_end") or "—"
    seq = profile.get("contract_seq_no") or 0
    count = profile.get("contract_count") or 1

    history = profile.get("contract_history")
    nomor_surat = ""
    if isinstance(history, list) and history:
        nomor_surat = history[-1].get("nomor_surat") or ""
    if not nomor_surat:
        try:
            dt = datetime.strptime(start_str, "%d %B %Y")
            roman_m = ROMAN_MONTHS[dt.month - 1]
            yr = dt.year
        except Exception:
            roman_m = "—"
            yr = datetime.now().year
        nomor_surat = f"{int(seq):04d}/DK.A/{roman_m}/{yr}"

    msg = await update.message.reply_text("Memuat gambar kontrak kerja aktif Anda...")
    png_bytes = await _render_kontrak_png(
        context, row, profile, start_str, end_str, nomor_surat, photo_bytes
    )

    if not png_bytes:
        await msg.edit_text("Gagal memuat gambar kontrak kerja.")
        return

    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"

    cap = (
        f"📑 <b>Kontrak Kerja (Aktif)</b>\n\n"
        f"• <b>Nama:</b> {name}\n"
        f"• <b>Jabatan:</b> {role_detail}\n"
        f"• <b>ID Staf:</b> <code>[ID: {int(seq):04d}]</code>\n"
        f"• <b>Periode:</b> {start_str} s/d {end_str}\n"
        f"• <b>Status:</b> Kontrak ke-{count} (Aktif)\n"
        f"• <b>Nomor:</b> <code>{nomor_surat}</code>\n\n"
        f"<i>Tanda tangan Anda telah sah dan tercatat aktif di sistem.</i>"
    )

    await msg.delete()
    await update.message.reply_photo(
        photo=BytesIO(png_bytes),
        filename="kontrak.png",
        caption=cap,
        parse_mode="HTML",
    )


async def _handle_new_kontrak_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    row: dict,
    profile: dict,
) -> None:
    fid = (profile.get("ttd_file_id") or "").strip()
    if not fid:
        await update.message.reply_text(
            "Tanda tangan belum tersedia. Silakan unggah terlebih dahulu menggunakan perintah:\n"
            "<code>/kontrak ttd</code>",
            parse_mode="HTML"
        )
        return

    photo_bytes = await _download_telegram_photo(context, fid)
    if not photo_bytes:
        await update.message.reply_text(
            "Gagal mengunduh tanda tangan dari server Telegram. Silakan unggah ulang TTD Anda dengan /kontrak ttd"
        )
        return

    now_ts = time.time()
    start_str, end_str, _ = calculate_contract_period(now_ts, is_new_or_renew=True)
    dt_now = datetime.fromtimestamp(now_ts)
    roman_m = ROMAN_MONTHS[dt_now.month - 1]
    nomor_surat_preview = f"DRAFT/DK.A/{roman_m}/{dt_now.year}"

    msg = await update.message.reply_text("Sedang menyiapkan draf kontrak kerja...")
    png_bytes = await _render_kontrak_png(
        context, row, profile, start_str, end_str, nomor_surat_preview, photo_bytes
    )

    if not png_bytes:
        await msg.edit_text("Gagal membuat gambar draf kontrak.")
        return

    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"

    cap = (
        f"📑 <b>Draf Kontrak Kerja Staf Baru</b>\n\n"
        f"• <b>Nama:</b> {name}\n"
        f"• <b>Jabatan:</b> {role_detail}\n"
        f"• <b>Rencana Periode:</b> {start_str} s/d {end_str}\n\n"
        f"Silakan periksa draf kontrak kerja Anda di atas.\n"
        f"Jika data dan tanda tangan Anda sudah sesuai, klik tombol di bawah atau ketik <code>/kontrak sahkan</code> "
        f"untuk meresmikan dan menerbitkan kontrak Anda."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✍️ Sahkan & Terbitkan Kontrak", callback_data="kontrak:sahkan"),
            InlineKeyboardButton("🔄 Ganti TTD", callback_data="kontrak:change_ttd"),
        ]
    ])

    await msg.delete()
    await update.message.reply_photo(
        photo=BytesIO(png_bytes),
        filename="draf_kontrak.png",
        caption=cap,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _execute_sahkan_kontrak(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    query=None,
) -> None:
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        if query:
            await query.answer("Hanya staf/internal.", show_alert=True)
        return

    profile = profile_from_row(row)
    now_ts = time.time()
    st = _get_contract_status(profile, now_ts)

    if st["is_active"]:
        msg_text = "Kontrak kerja Anda sudah aktif dan sah."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    fid = (profile.get("ttd_file_id") or "").strip()
    if not fid:
        msg_text = "Tanda tangan belum tersedia. Silakan unggah terlebih dahulu dengan /kontrak ttd."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    photo_bytes = await _download_telegram_photo(context, fid)
    if not photo_bytes:
        msg_text = "Gagal mengunduh tanda tangan. Silakan unggah ulang dengan /kontrak ttd."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    if query:
        await query.answer("Memproses pengesahan kontrak...")

    # Ambil sequence number atomic resmi
    seq = await db.get_next_contract_seq(conn)
    start_str, end_str, end_ts = calculate_contract_period(now_ts, is_new_or_renew=True)

    dt_now = datetime.fromtimestamp(now_ts)
    roman_month = ROMAN_MONTHS[dt_now.month - 1]
    nomor_surat = f"{seq:04d}/DK.A/{roman_month}/{dt_now.year}"
    signed_str = f"{dt_now.day} {MONTH_NAMES[dt_now.month - 1]} {dt_now.year} {dt_now.strftime('%H:%M')}"

    history = [
        {
            "iteration": 1,
            "period": f"{start_str} s/d {end_str}",
            "nomor_surat": nomor_surat,
            "signed_at": signed_str,
        }
    ]

    await db.set_profile_partial(conn, uid, {
        "internal_since": start_str,
        "contract_count": 1,
        "contract_start": start_str,
        "contract_end": end_str,
        "contract_end_ts": end_ts,
        "contract_seq_no": seq,
        "contract_history": history,
    })

    profile["contract_seq_no"] = seq
    profile["contract_start"] = start_str
    profile["contract_end"] = end_str
    profile["contract_count"] = 1
    png_bytes = await _render_kontrak_png(
        context, row, profile, start_str, end_str, nomor_surat, photo_bytes
    )

    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"
    username_str = f"@{row['username']}" if row["username"] else "—"

    cap = (
        f"🎉 <b>Selamat! Kontrak Kerja Resmi Diterbitkan</b>\n\n"
        f"• <b>Nama:</b> {name}\n"
        f"• <b>Jabatan:</b> {role_detail}\n"
        f"• <b>ID Staf:</b> <code>[ID: {seq:04d}]</code>\n"
        f"• <b>Nomor Surat:</b> <code>{nomor_surat}</code>\n"
        f"• <b>Periode:</b> {start_str} s/d {end_str}\n"
        f"• <b>Status:</b> Kontrak ke-1 (Aktif)"
    )

    target_chat = update.effective_chat
    if png_bytes:
        await context.bot.send_photo(
            chat_id=target_chat.id,
            photo=BytesIO(png_bytes),
            filename="kontrak.png",
            caption=cap,
            parse_mode="HTML",
        )
    else:
        await context.bot.send_message(chat_id=target_chat.id, text=cap, parse_mode="HTML")

    if OWNER_ID and str(OWNER_ID) != "0":
        try:
            owner_cap = (
                f"🔔 <b>Notifikasi Kontrak Staf Baru</b>\n\n"
                f"Staf <b>{name}</b> {username_str} telah mengesahkan kontrak kerja pertamanya.\n"
                f"• <b>ID Staf:</b> <code>[ID: {seq:04d}]</code>\n"
                f"• <b>Nomor Surat:</b> <code>{nomor_surat}</code>\n"
                f"• <b>Periode:</b> {start_str} s/d {end_str}\n"
                f"• <b>Status:</b> Kontrak ke-1"
            )
            if png_bytes:
                await context.bot.send_photo(
                    chat_id=OWNER_ID,
                    photo=BytesIO(png_bytes),
                    caption=owner_cap,
                    parse_mode="HTML",
                )
            else:
                await context.bot.send_message(chat_id=OWNER_ID, text=owner_cap, parse_mode="HTML")
        except Exception as e:
            log.warning("Gagal mengirim notif kontrak ke owner: %s", e)


async def cmd_kontrak_renew(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query=None,
) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not update.effective_user or not chat_id:
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        if query:
            await query.answer("Hanya staf/internal.", show_alert=True)
        else:
            await update.message.reply_text("Hanya staf/internal.")
        return

    profile = profile_from_row(row)
    c_seq = profile.get("contract_seq_no")
    c_end_ts = profile.get("contract_end_ts")
    now_ts = time.time()

    if not c_seq or not c_end_ts:
        msg_text = "Anda belum memiliki kontrak sebelumnya. Silakan ketik /kontrak saya untuk membuat kontrak pertama Anda."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    st = _get_contract_status(profile, now_ts)
    if st["is_active"]:
        c_end = profile.get("contract_end") or "—"
        days_left = max(1, int((float(c_end_ts) - now_ts) / 86400))
        msg_text = (
            f"ℹ️ Kontrak Anda masih aktif hingga <b>{c_end}</b> (sisa {days_left} hari).\n\n"
            f"Perpanjangan kontrak hanya dapat dilakukan mulai <b>H-7</b> sebelum masa kontrak berakhir."
        )
        if query:
            await query.answer("Kontrak Anda masih aktif.", show_alert=True)
            await context.bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML")
        else:
            await update.message.reply_text(msg_text, parse_mode="HTML")
        return

    fid = (profile.get("ttd_file_id") or "").strip()
    if not fid:
        msg_text = "Tanda tangan belum tersedia. Silakan unggah tanda tangan terlebih dahulu dengan /kontrak ttd."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    photo_bytes = await _download_telegram_photo(context, fid)
    if not photo_bytes:
        msg_text = "Gagal mengunduh tanda tangan dari server Telegram. Silakan unggah ulang dengan /kontrak ttd."
        if query:
            await query.answer(msg_text, show_alert=True)
        else:
            await update.message.reply_text(msg_text)
        return

    if query:
        await query.answer("Memperbarui kontrak...")

    seq = int(c_seq)
    current_count = int(profile.get("contract_count") or 1)
    new_count = current_count + 1

    start_str, end_str, end_ts = calculate_contract_period(now_ts, is_new_or_renew=True)
    dt_now = datetime.fromtimestamp(now_ts)
    roman_month = ROMAN_MONTHS[dt_now.month - 1]
    nomor_surat = f"{seq:04d}/DK.A/{roman_month}/{dt_now.year}"
    signed_str = f"{dt_now.day} {MONTH_NAMES[dt_now.month - 1]} {dt_now.year} {dt_now.strftime('%H:%M')}"

    history = profile.get("contract_history")
    if not isinstance(history, list):
        history = []

    if not history and profile.get("contract_start"):
        history.append({
            "iteration": current_count,
            "period": f"{profile.get('contract_start')} s/d {profile.get('contract_end')}",
            "nomor_surat": f"{seq:04d}/DK.A/—/{str(profile.get('contract_start', ''))[-4:]}",
            "signed_at": profile.get("contract_start"),
        })

    history.append({
        "iteration": new_count,
        "period": f"{start_str} s/d {end_str}",
        "nomor_surat": nomor_surat,
        "signed_at": signed_str,
    })

    await db.set_profile_partial(conn, uid, {
        "contract_count": new_count,
        "contract_start": start_str,
        "contract_end": end_str,
        "contract_end_ts": end_ts,
        "contract_history": history,
    })

    profile["contract_count"] = new_count
    profile["contract_start"] = start_str
    profile["contract_end"] = end_str
    png_bytes = await _render_kontrak_png(
        context, row, profile, start_str, end_str, nomor_surat, photo_bytes
    )

    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"
    username_str = f"@{row['username']}" if row["username"] else "—"

    cap = (
        f"✅ <b>Kontrak Kerja Berhasil Diperbarui!</b>\n\n"
        f"• <b>Nama:</b> {name}\n"
        f"• <b>Jabatan:</b> {role_detail}\n"
        f"• <b>ID Staf:</b> <code>[ID: {seq:04d}]</code>\n"
        f"• <b>Periode Baru:</b> {start_str} s/d {end_str}\n"
        f"• <b>Status:</b> Kontrak ke-{new_count}\n"
        f"• <b>Nomor Surat:</b> <code>{nomor_surat}</code>"
    )

    if png_bytes:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=BytesIO(png_bytes),
            filename="kontrak.png",
            caption=cap,
            parse_mode="HTML",
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=cap, parse_mode="HTML")

    if OWNER_ID and str(OWNER_ID) != "0":
        try:
            owner_cap = (
                f"🔔 <b>Notifikasi Perpanjangan Kontrak</b>\n\n"
                f"Staf <b>{name}</b> {username_str} telah memperbarui kontrak kerjanya.\n"
                f"• <b>ID Staf:</b> <code>[ID: {seq:04d}]</code>\n"
                f"• <b>Nomor:</b> <code>{nomor_surat}</code>\n"
                f"• <b>Periode:</b> {start_str} s/d {end_str}\n"
                f"• <b>Status:</b> Kontrak ke-{new_count}"
            )
            if png_bytes:
                await context.bot.send_photo(
                    chat_id=OWNER_ID,
                    photo=BytesIO(png_bytes),
                    caption=owner_cap,
                    parse_mode="HTML",
                )
            else:
                await context.bot.send_message(chat_id=OWNER_ID, text=owner_cap, parse_mode="HTML")
        except Exception as e:
            log.warning("Gagal mengirim notif kontrak renew ke owner: %s", e)


async def cmd_kontrak_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Hanya admin dan owner yang bisa melihat daftar semua kontrak.")
        return

    cur = await conn.execute(
        "SELECT telegram_id, username, first_name, role, profile_json FROM users WHERE role IN (?, ?)",
        (ROLE_INTERNAL, ROLE_ADMIN),
    )
    db_rows = await cur.fetchall()

    if not db_rows:
        await update.message.reply_text("Tidak ada staf internal terdaftar.")
        return

    def sort_key(r):
        p = profile_from_row(r)
        seq = p.get("contract_seq_no")
        seq_val = seq if isinstance(seq, int) else 999999
        name_val = (p.get("full_name") or r["first_name"] or "").lower()
        return (seq_val, name_val)

    rows = sorted(db_rows, key=sort_key)

    now_ts = time.time()
    _, end_str, _ = calculate_contract_period(now_ts, is_new_or_renew=False)

    lines = [
        "📑 <b>Daftar Kontrak Staf Internal</b>",
        f"Akhir Periode Organisasi: {end_str}",
        "",
    ]

    for r in rows:
        p = profile_from_row(r)
        name = (p.get("full_name") or r["first_name"] or "Tanpa Nama").strip()
        uname = f"(@{r['username']})" if r["username"] else ""

        st = _get_contract_status(p, now_ts)
        c_seq = p.get("contract_seq_no")
        c_count = p.get("contract_count") or (1 if c_seq else 0)
        since = p.get("internal_since") or p.get("contract_start") or ""

        seq_str = f"[ID: {int(c_seq):04d}] " if isinstance(c_seq, int) else "[ID: —] "
        count_str = f" • Ke-{c_count}" if c_seq else ""
        since_str = f" • Sejak {since}" if since else ""

        user_line = f"• {st['status_icon']} {seq_str}<b>{name}</b> {uname}{count_str}{since_str}".strip()
        lines.append(user_line)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n...(terpotong)"

    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_kontrak_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target: str,
) -> None:
    conn = _conn(context)
    db = _db(context)

    target_ids = []
    if target.isdigit():
        seq_target = int(target)
        cur = await conn.execute("SELECT telegram_id, profile_json FROM users")
        rows = await cur.fetchall()
        for r in rows:
            p = json.loads(r["profile_json"] or "{}")
            if p.get("contract_seq_no") == seq_target:
                target_ids.append(r["telegram_id"])
                break

    if not target_ids:
        target_ids = await db.find_ids_by_usernames(conn, [target])

    if not target_ids:
        await update.message.reply_text("User atau ID kontrak tidak ditemukan.")
        return

    target_uid = target_ids[0]
    t_row = await user_row(conn, db, target_uid)
    if not t_row:
        await update.message.reply_text("Data staf tidak ditemukan di sistem.")
        return

    t_profile = profile_from_row(t_row)
    now_ts = time.time()
    st = _get_contract_status(t_profile, now_ts)

    name = (t_profile.get("full_name") or t_row["first_name"] or "Tanpa Nama").strip()
    pd_raw = t_profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"
    username_str = f"@{t_row['username']}" if t_row["username"] else "—"

    fid = (t_profile.get("ttd_file_id") or "").strip()
    photo_bytes = await _download_telegram_photo(context, fid) if fid else None

    c_seq = t_profile.get("contract_seq_no")
    c_start = t_profile.get("contract_start") or "—"
    c_end = t_profile.get("contract_end") or "—"
    c_count = t_profile.get("contract_count") or (1 if c_seq else 0)
    since = t_profile.get("internal_since") or t_profile.get("contract_start") or "—"
    history = t_profile.get("contract_history") or []

    seq_disp = f"{int(c_seq):04d}" if c_seq else "BELUM_TERDAFTAR"
    nomor_surat = ""
    if isinstance(history, list) and history:
        nomor_surat = history[-1].get("nomor_surat") or ""
    if not nomor_surat and c_seq:
        nomor_surat = f"{int(c_seq):04d}/DK.A/—/{datetime.now().year}"

    msg = await update.message.reply_text("Memuat data & gambar kontrak...")
    png_bytes = await _render_kontrak_png(
        context, t_row, t_profile, c_start, c_end, nomor_surat, photo_bytes
    )

    cap = f"Kontrak (Admin View) - {name}\nPeriode: {c_start} s/d {c_end}"

    if png_bytes:
        await update.message.reply_photo(
            photo=BytesIO(png_bytes),
            filename="kontrak.png",
            caption=cap,
        )

    # Kirim rangkuman data tulis lengkap
    history_lines = []
    if isinstance(history, list) and history:
        for item in history:
            itr = item.get("iteration", "—")
            prd = item.get("period", "—")
            ns = item.get("nomor_surat", "—")
            history_lines.append(f"  {itr}. <code>{ns}</code> ({prd})")
    elif c_seq:
        history_lines.append(f"  1. <code>{nomor_surat}</code> ({c_start} s/d {c_end})")
    else:
        history_lines.append("  <i>Belum ada riwayat tanda tangan.</i>")

    hist_str = "\n".join(history_lines)
    text_info = (
        f"📋 <b>Detail Informasi Kontrak Staf</b>\n\n"
        f"• <b>Nama:</b> {name} ({username_str})\n"
        f"• <b>Jabatan:</b> {role_detail}\n"
        f"• <b>ID Staf:</b> <code>[ID: {seq_disp}]</code>\n"
        f"• <b>Internal Sejak:</b> {since}\n"
        f"• <b>Status Kontrak:</b> {st['status_icon']} {st['status_label']} (Kontrak ke-{c_count})\n"
        f"• <b>Masa Berlaku:</b> {c_start} s/d {c_end}\n\n"
        f"📜 <b>Riwayat Penandatanganan Kontrak:</b>\n{hist_str}"
    )

    await msg.delete()
    await update.message.reply_text(text_info, parse_mode="HTML")


async def cb_kontrak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    data = query.data
    action = data.split(":", 1)[1] if ":" in data else ""
    uid = query.from_user.id

    if action == "sahkan":
        await _execute_sahkan_kontrak(update, context, uid, query=query)
    elif action == "renew":
        await cmd_kontrak_renew(update, context, query=query)
    elif action == "change_ttd":
        conn = _conn(context)
        db = _db(context)
        await db.set_onboarding_step(conn, uid, STEP_KONTRAK_TTD)
        await query.answer()
        await query.message.reply_text(
            "✍️ <b>Pengisian Tanda Tangan</b>\n\n"
            "Silakan kirim tanda tangan digital Anda dalam bentuk foto (bukan file).\n\n"
            "<b>Tanda tangan harus berwarna hitam dengan background putih.</b>",
            parse_mode="HTML"
        )


async def cmd_kontrak_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    if row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Fitur kontrak hanya untuk staf internal.")
        return

    def _show_menu():
        admin_menu = ""
        if row["role"] in (ROLE_ADMIN, ROLE_OWNER):
            admin_menu = (
                "<code>/kontrak all</code> — Lihat daftar kontrak staf\n"
                "<code>/kontrak check &lt;id/username&gt;</code> — Cek detail kontrak per orang\n"
            )
        return update.message.reply_text(
            "<b>Menu Kontrak:</b>\n"
            "<code>/kontrak saya</code> — Lihat draf/kontrak kerja Anda\n"
            "<code>/kontrak ttd</code> — Upload tanda tangan baru\n"
            "<code>/kontrak sahkan</code> — Sahkan draf kontrak pertama\n"
            "<code>/kontrak renew</code> — Perbarui masa kontrak\n"
            + admin_menu,
            parse_mode="HTML"
        )

    if not context.args:
        await _show_menu()
        return

    subcmd = context.args[0].lower()

    if subcmd == "saya":
        profile = profile_from_row(row)
        now_ts = time.time()
        st = _get_contract_status(profile, now_ts)

        if st["is_expiring"] or st["is_expired"]:
            c_end = profile.get("contract_end") or "—"
            status_text = "telah berakhir" if st["is_expired"] else f"akan segera berakhir pada <b>{c_end}</b>"
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Perbarui Kontrak (Renew)", callback_data="kontrak:renew"),
                    InlineKeyboardButton("✍️ Ganti TTD Dulu", callback_data="kontrak:change_ttd"),
                ]
            ])
            await update.message.reply_text(
                f"⏳ <b>Kontrak Berakhir</b>\n\n"
                f"Masa kontrak Anda periode ini {status_text}.\n"
                f"Apakah Anda ingin memperbarui kontrak untuk periode berikutnya?\n\n"
                f"• Klik tombol di bawah atau ketik <code>/kontrak renew</code> untuk langsung memperbarui.\n"
                f"• Ketik <code>/kontrak ttd</code> jika Anda ingin mengganti tanda tangan terlebih dahulu.",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return

        if st["is_active"]:
            await _send_active_kontrak(update, context, uid, row, profile)
            return

        # Staf baru belum punya kontrak resmi
        await _handle_new_kontrak_draft(update, context, uid, row, profile)

    elif subcmd == "sahkan":
        await _execute_sahkan_kontrak(update, context, uid, query=None)
    elif subcmd == "ttd":
        await cmd_kontrak_ttd(update, context)
    elif subcmd == "renew":
        await cmd_kontrak_renew(update, context, query=None)
    elif subcmd == "all":
        await cmd_kontrak_all(update, context)
    elif subcmd == "check":
        if row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
            await update.message.reply_text("Tidak diizinkan.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("Gunakan: /kontrak check @username atau /kontrak check <id>")
            return
        await cmd_kontrak_check(update, context, context.args[1])
    else:
        await _show_menu()
