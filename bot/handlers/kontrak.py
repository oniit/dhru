"""Perintah /kontrak — manajemen kontrak internal."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, filters

from bot.database import ROLE_ADMIN, ROLE_INTERNAL, ROLE_OWNER, Database
from bot.kontrak_card import render_kontrak_png_bytes
from bot.settings import CHOICES, multi_choice_labels

from .common import profile_from_row, user_row, role_display

log = logging.getLogger(__name__)

STEP_KONTRAK_TTD = "KONTRAK_TTD"


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


def calculate_contract_period(start_timestamp: float) -> tuple[str, str, float]:
    """Mengembalikan rentang tanggal kontrak (start, end) dan end_timestamp.
    Start: Hari ini. End: Tanggal 17 Bulan Genap Terdekat di masa depan.
    """
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", 
              "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    
    dt_start = datetime.fromtimestamp(start_timestamp)
    start_str = f"{dt_start.day} {months[dt_start.month - 1]} {dt_start.year}"
    
    y = dt_start.year
    m = dt_start.month
    d = dt_start.day
    
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
                
    end_str = f"17 {months[end_m - 1]} {y}"
    dt_end = datetime(y, end_m, 17, 23, 59, 59)
    end_ts = dt_end.timestamp()
    
    return start_str, end_str, end_ts


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
        "Silakan tulis tanda tangan Anda dengan pulpen hitam/biru di atas <b>kertas putih bersih</b>.\n"
        "Lalu foto dan kirimkan gambar tersebut ke chat ini.\n\n"
        "<i>Pastikan cahaya cukup terang dan tidak ada bayangan pada kertas agar hasil di kontrak terlihat menyatu.</i>"
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
    await update.message.reply_text(
        "✅ Tanda tangan berhasil disimpan! Silakan ketik /kontrak untuk melihat dan menghasilkan kontrak kerja Anda."
    )


async def _generate_and_send_kontrak(
    update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, start_ts: float, is_admin_check: bool = False
) -> None:
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        return
    
    profile = profile_from_row(row)
    fid = (profile.get("ttd_file_id") or "").strip()
    if not fid:
        if not is_admin_check:
            await update.message.reply_text("Tanda tangan belum tersedia. Silakan unggah terlebih dahulu menggunakan perintah:\n/kontrak ttd")
        else:
            await update.message.reply_text(f"Staf tersebut (ID {uid}) belum mengunggah tanda tangan kontrak.")
        return
        
    photo_bytes = await _download_telegram_photo(context, fid)
    if not photo_bytes:
        await update.message.reply_text("Gagal mengunduh tanda tangan dari server Telegram. Silakan unggah ulang TTD Anda dengan /kontrak ttd")
        return

    # Ambil detail nama dan jabatan
    name = (profile.get("full_name") or row["first_name"] or "Tanpa Nama").strip()
    
    # Detail jabatan (mirip dengan Karpeg)
    pd_raw = profile.get("position_detail")
    role_detail = multi_choice_labels("position_details", pd_raw if isinstance(pd_raw, list) else [pd_raw] if pd_raw else []) or "—"
    
    # Hitung periode
    start_str, end_str, end_ts = calculate_contract_period(start_ts)
    period_str = f"{start_str} s/d {end_str}"
    
    # Ambil username
    username_str = f"@{update.effective_user.username}" if update.effective_user.username else "—"
    
    msg = await update.message.reply_text("Sedang meng-generate kontrak, mohon tunggu...")
    
    try:
        png_bytes = render_kontrak_png_bytes(
            name=name,
            role_detail=role_detail,
            username=username_str,
            start_date_str=start_str,
            end_date_str=end_str,
            ttd_bytes=photo_bytes,
        )
    except Exception as e:
        log.exception("render kontrak gagal uid=%s", uid)
        await msg.edit_text("Gagal membuat gambar Kontrak. Pastikan template kontrak.png tersedia.")
        return

    # Simpan periode ke profil jika bukan admin check
    if not is_admin_check:
        await db.set_profile_partial(conn, uid, {
            "contract_start": start_str,
            "contract_end": end_str,
            "contract_end_ts": end_ts,
        })
    
    cap = f"Kontrak Kerja ({role_detail})\nNama: {name}\nPeriode: {period_str}"
    if is_admin_check:
        cap = f"Kontrak (Admin View) - {name}\nPeriode: {period_str}"

    await msg.delete()
    await update.message.reply_photo(
        photo=BytesIO(png_bytes),
        filename="kontrak.png",
        caption=cap,
    )


async def cmd_kontrak_renew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Hanya staf/internal.")
        return
        
    await update.message.reply_text("Memperbarui kontrak untuk periode berikutnya...")
    await _generate_and_send_kontrak(update, context, uid, time.time(), is_admin_check=False)


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
        "SELECT telegram_id, username, first_name, role, profile_json FROM users WHERE role IN (?, ?) ORDER BY first_name ASC",
        (ROLE_INTERNAL, ROLE_ADMIN)
    )
    rows = await cur.fetchall()
    
    if not rows:
        await update.message.reply_text("Tidak ada staf internal terdaftar.")
        return
        
    lines = ["📑 <b>Daftar Kontrak Staf Internal</b>", ""]
    now_ts = time.time()
    
    for r in rows:
        p = profile_from_row(r)
        name = (p.get("full_name") or r["first_name"] or "Tanpa Nama").strip()
        uname = f"(@{r['username']})" if r["username"] else ""
        
        has_ttd = bool((p.get("ttd_file_id") or "").strip())
        c_start = p.get("contract_start")
        c_end = p.get("contract_end")
        c_end_ts = p.get("contract_end_ts")
        
        status = "❌ Belum TTD"
        if has_ttd:
            if not c_end_ts:
                status = "⚠️ Sudah TTD (Belum Generate)"
            elif now_ts > float(c_end_ts):
                status = "Expired"
            elif (float(c_end_ts) - now_ts) < (7 * 24 * 3600):
                status = "Menjelang Expired"
            else:
                status = "Aktif"
                
        period_info = f"{c_start} - {c_end}" if c_end else "—"
        lines.append(f"• <b>{name}</b> {uname}")
        lines.append(f"  Status: {status} | Periode: {period_info}")
        
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n...(terpotong)"
        
    await update.message.reply_text(text)


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
        
    if not context.args:
        profile = profile_from_row(row)
        fid = (profile.get("ttd_file_id") or "").strip()
        if not fid:
            await update.message.reply_text(
                "Tanda tangan Anda belum tersedia.\n"
                "Silakan unggah terlebih dahulu menggunakan perintah:\n"
                "<code>/kontrak ttd</code>"
            )
            return
            
        c_end_ts = profile.get("contract_end_ts")
        now_ts = time.time()
        
        needs_renewal = False
        if c_end_ts:
            if now_ts > float(c_end_ts):
                needs_renewal = True
            elif (float(c_end_ts) - now_ts) < (7 * 24 * 3600): # H-7
                needs_renewal = True
                
        if needs_renewal:
            await update.message.reply_text(
                "⏳ <b>Kontrak Berakhir</b>\n\n"
                "Masa kontrak Anda periode ini telah atau akan segera berakhir.\n"
                "Apakah Anda ingin memperbarui kontrak untuk periode berikutnya?\n\n"
                "Ketik <code>/kontrak renew</code> untuk menggunakan TTD lama Anda secara instan.\n"
                "Atau ketik <code>/kontrak ttd</code> jika Anda ingin mengubah foto tanda tangan Anda."
            )
            return
            
        # Jika masih aktif atau baru pertama kali punya TTD tapi belum pernah generate
        await _generate_and_send_kontrak(update, context, uid, now_ts, is_admin_check=False)
        return

    subcmd = context.args[0].lower()
    
    if subcmd == "ttd":
        await cmd_kontrak_ttd(update, context)
    elif subcmd == "renew":
        await cmd_kontrak_renew(update, context)
    elif subcmd == "all":
        await cmd_kontrak_all(update, context)
    elif subcmd == "check":
        if row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
            await update.message.reply_text("Tidak diizinkan.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("Gunakan: /kontrak check @username")
            return
        target = context.args[1]
        target_ids = await db.find_ids_by_usernames(conn, [target])
        if not target_ids:
            await update.message.reply_text("User tidak ditemukan.")
            return
        await _generate_and_send_kontrak(update, context, target_ids[0], time.time(), is_admin_check=True)
    else:
        await update.message.reply_text(
            "<b>Menu Kontrak:</b>\n"
            "<code>/kontrak</code> — Generate/Lihat kontrak kerja\n"
            "<code>/kontrak ttd</code> — Upload tanda tangan baru\n"
            "<code>/kontrak renew</code> — Perbarui masa kontrak\n"
            + ("<code>/kontrak all</code> — Lihat daftar kontrak staf\n" if row["role"] in (ROLE_ADMIN, ROLE_OWNER) else "")
        )
