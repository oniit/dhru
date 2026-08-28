from __future__ import annotations

import asyncio
import html
import json
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import random
import string
import time

from bot.agra_parse import parse_add_command
from bot.setrole_parse import parse_setrole_command
from bot.database import (
    ROLE_ADMIN,
    ROLE_INTERNAL,
    ROLE_OWNER,
    ROLE_STUDENT,
    ROLE_BEM,
    ROLE_MABA,
    ROLE_PUBLIC,
)
from bot.settings import (
    CHOICES,
    ADMIN_IDS,
    OWNER_ID,
    PROFILE_FIELDS,
    field_applies_to_role,
    filtered_choice_items,
    is_choice_allowed_for_profile,
    is_owner,
)
from bot.timefmt import format_local_time, days_until_next_birthday

from .common import (
    field_label_for_key,
    fields_for_role,
    format_profile_card,
    keyboard_for_choices,
    keyboard_for_multi_choices,
    missing_required_fields,
    moderator_chat_ids,
    optional_fields_still_open,
    profile_from_row,
    normalize_multi_choice_value,
    role_display,
    sync_roles_from_env,
    user_row,
    is_dekan_profile,
    can_daftar_as_dean,
    user_in_dean_faculty_scope,
    dean_faculty_id,
    can_daftar_as_lecturer,
    lecturer_class_ids,
    user_in_lecturer_scope,
    can_manage_agra,
    can_assign_roles,
    can_approve_profile,
    can_view_sensitive_logs,
    can_report,
    can_tag_all,
    presence_allowed_class_ids,
)

MULTI_UD_KEY = "multi_select"
ADMIN_TARGET_KEY = "admin_profile_target"
LENGKAPI_DONE_KEY = "__lengkapi_done"

ORRESET_SCOPE_KEY = "owner_reset_scope"


def _multi_clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(MULTI_UD_KEY, None)


def _multi_init(
    context: ContextTypes.DEFAULT_TYPE,
    field_key: str,
    flow: str,
    profile: dict,
) -> None:
    ids = normalize_multi_choice_value(profile.get(field_key))
    context.user_data[MULTI_UD_KEY] = {
        "field": field_key,
        "ids": set(ids),
        "flow": flow,
    }

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _is_lengkapi_done(profile: dict) -> bool:
    return bool(profile.get(LENGKAPI_DONE_KEY))


def _display_name_from_row(row) -> str:
    if not row:
        return "—"
    profile = profile_from_row(row)
    return (
        profile.get("full_name")
        or f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        or (f"@{row['username']}" if row["username"] else str(row["telegram_id"]))
    )


def _profile_request_status_text(
    original_text: str,
    *,
    status: str,
    decided_by_name: str,
) -> str:
    return f"{original_text}\n\nStatus: {status}.\nOleh: {decided_by_name}"


async def _broadcast_profile_request_status(
    context: ContextTypes.DEFAULT_TYPE,
    db,
    conn,
    request_id: int,
    *,
    status: str,
    decided_by_name: str,
    fallback_base_text: str,
) -> bool:
    """Edit semua pesan moderasi untuk pengajuan ini. True jika ada pesan terdaftar."""
    req = await db.get_profile_request(conn, request_id)
    stored = None
    if req:
        stored = dict(req).get("moderator_prompt_text")
    base = (stored or "").strip() or fallback_base_text
    refs = await db.list_profile_request_mod_messages(conn, request_id)
    if not refs:
        return False
    final_text = _profile_request_status_text(
        base, status=status, decided_by_name=decided_by_name
    )
    for r in refs:
        cid = int(r["mod_chat_id"])
        mid = int(r["message_id"])
        try:
            await context.bot.edit_message_text(
                chat_id=cid,
                message_id=mid,
                text=final_text,
                reply_markup=None,
            )
        except Exception as e:
            log.warning("profile req broadcast %s/%s: %s", cid, mid, e)
    return True


async def _mark_lengkapi_done_if_complete(conn, db, telegram_id: int) -> None:
    row = await user_row(conn, db, telegram_id)
    if not row:
        return
    profile = profile_from_row(row)
    if _is_lengkapi_done(profile):
        return
    if not missing_required_fields(profile, row["role"]):
        await db.set_profile_partial(conn, telegram_id, {LENGKAPI_DONE_KEY: True})


async def _revalidate_filtered_choice_fields(
    conn, db, telegram_id: int
) -> None:
    """Hapus nilai choice yang tidak lagi valid (mis. jurusan salah fakultas)."""
    row = await user_row(conn, db, telegram_id)
    if not row:
        return
    prof = profile_from_row(row)
    to_remove: list[str] = []
    role = row["role"]
    for f in PROFILE_FIELDS:
        if not field_applies_to_role(f, role, prof):
            if f.key == "bem_position" and role == ROLE_STUDENT:
                continue
            if f.key in prof:
                to_remove.append(f.key)
        else:
            if f.type == "choice" and f.filter_by_field:
                val = prof.get(f.key)
                if val is not None and val != "":
                    if not is_choice_allowed_for_profile(f, prof, str(val)):
                        to_remove.append(f.key)
    if to_remove:
        await db.remove_profile_keys(conn, telegram_id, to_remove)
    if not is_dekan_profile(prof) and (prof.get("staff_faculty") or "").strip():
        await db.remove_profile_keys(conn, telegram_id, ["staff_faculty"])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    u = update.effective_user
    conn = _conn(context)
    db = _db(context)
    await sync_roles_from_env(db, conn)

    raw = {
        "id": u.id,
        "is_bot": u.is_bot,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "username": u.username,
        "language_code": u.language_code,
        "is_premium": getattr(u, "is_premium", None),
        "added_to_attachment_menu": getattr(u, "added_to_attachment_menu", None),
        "can_connect_to_business": getattr(u, "can_connect_to_business", None),
        "allows_write_to_pm": getattr(u, "allows_write_to_pm", None),
    }
    await db.upsert_user_from_telegram(
        conn,
        telegram_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name,
        language_code=u.language_code,
        is_premium=bool(getattr(u, "is_premium", False)),
        is_bot=u.is_bot,
        raw_profile={k: v for k, v in raw.items() if v is not None},
    )
    await db.set_onboarding_step(conn, u.id, None)
    await _revalidate_filtered_choice_fields(conn, db, u.id)
    row = await user_row(conn, db, u.id)
    profile = profile_from_row(row)
    role = row["role"] if row else ROLE_PUBLIC
    
    parts = update.message.text.split()
    if len(parts) > 1 and parts[1].startswith("rempah_"):
        chat_id_str = parts[1][7:]
        await db.set_onboarding_step(conn, u.id, f"REMPAH_SETOR:{chat_id_str}")
        await update.message.reply_text("Silakan ketikkan angka nominal setoran rempah Anda (0-10):")
        return
        
    if role == ROLE_PUBLIC:
        buttons = []
        if not _is_lengkapi_done(profile):
            buttons.append([InlineKeyboardButton("🎓 Daftar Akun Mahasiswa Baru", callback_data="maba:start")])
            
        buttons.extend([
            [InlineKeyboardButton("👤 Daftar Akun Publik", callback_data="openlt:full_name")],
            [InlineKeyboardButton("📦 Pakai Kode Akademik", callback_data="pub:kode")],
            [InlineKeyboardButton("📞 Hubungi Instansi", callback_data="pub:hubungi")],
            [InlineKeyboardButton("💬 Pertanyaan Lainnya", callback_data="pub:lainnya")]
        ])
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Selamat datang! Silakan pilih menu berikut:", reply_markup=keyboard)
        return

    miss = missing_required_fields(profile, role)

    lines = [
        "Halo! Profil Telegram kamu sudah dicatat.",
        "",
        "Gunakan /lengkapi untuk melengkapi data bertahap, "
        "/ubah untuk mengajukan perubahan (perlu persetujuan admin), "
        "dan /profile untuk melihat profil.",
        "",
        "Perintah lain: /help",
    ]
    if miss:
        lines.append("")
        lines.append(f"📋 Masih kurang {len(miss)} data wajib — ketik /lengkapi.")

    await update.message.reply_text("\n".join(lines))


async def cmd_maba(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command untuk mendaftar sebagai Mahasiswa Baru (terutama bagi user publik lama)."""
    u = update.effective_user
    if not u:
        return
    conn = _conn(context)
    db = _db(context)
    
    await db.set_onboarding_step(conn, u.id, "MABA_NAME")
    await update.message.reply_text(
        "Ketikkan Nama Lengkap Anda:"
    )


async def cmd_kode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    await db.set_onboarding_step(conn, update.effective_user.id, "INPUT_CODE")
    await update.message.reply_text("Silakan ketikkan/tempel kode akses (huruf besar) yang Anda terima dari pihak akademik:")


async def cmd_gencode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] != ROLE_OWNER:
        await update.message.reply_text("Tidak diizinkan.")
        return
    
    parts = update.message.text.split()
    count = 1
    target_role = "student"
    
    if len(parts) > 1 and parts[1].isdigit():
        count = int(parts[1])
    if len(parts) > 2:
        target_role = parts[2].lower()
        if target_role not in (ROLE_ADMIN, ROLE_INTERNAL, ROLE_BEM, ROLE_STUDENT, ROLE_MABA):
            await update.message.reply_text("Role target tidak valid. Gunakan: admin, internal, bem, student, atau maba.")
            return

    if count > 100: count = 100
    
    codes = []
    now = time.time()
    for _ in range(count):
        codes.append((''.join(random.choices(string.ascii_uppercase + string.digits, k=10)), now, target_role))
    
    await conn.executemany("INSERT INTO access_codes (code, created_at, target_role) VALUES (?, ?, ?)", codes)
    await conn.commit()
    
    await update.message.reply_text(f"Berhasil generate {count} kode akses (Role: {target_role}):\n\n" + "\n".join(f"<code>{c[0]}</code>" for c in codes))


async def cmd_gencode_avail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] != ROLE_OWNER:
        await update.message.reply_text("Tidak diizinkan.")
        return
    
    cur = await conn.execute("SELECT code, target_role FROM access_codes WHERE used_by IS NULL ORDER BY created_at DESC")
    rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Tidak ada kode akses yang tersedia (belum diklaim).")
        return
        
    text = f"Terdapat {len(rows)} kode akses yang belum diklaim:\n\n"
    text += "\n".join(f"<code>{r['code']}</code> (Role: {r['target_role']})" for r in rows)
    
    if len(text) > 4000:
        text = text[:4000] + "\n\n...(terpotong karena terlalu panjang)"
        
    await update.message.reply_text(text)


def help_for_role(role: str, profile: dict | None = None) -> str:
    prof = profile if profile is not None else {}
    allowed_classes = presence_allowed_class_ids(role, prof)
    can_open_presensi = allowed_classes is None or len(allowed_classes) > 0

    lines = [
        "<b>Perintah umum</b>",
        "/start — Daftar & sinkron profil Telegram",
        "/profile — Profil akun & total Agra",
        "/lengkapi — Isi data wajib awal (sekali)",
        "/ubah — Ajukan perubahan (disetujui admin)",
        "",
    ]
    if role in (ROLE_STUDENT, ROLE_BEM):
        lines.append(
            "<b>Mahasiswa</b>\n/hadir — Presensi ke sesi yang dibuka\n"
            "/tugas — Menu & Dashboard Tugas\n"
            "/ktm — Kartu tanda mahasiswa\n"
        )
    if role in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        lines.append(
            "<b>Staf / Pengajar</b>\n"
            "/tugas — Menu Buka/Kelola Tugas\n"
            "/karpeg — Kartu Pegawai\n"
            "/kontrak — Kontrak Kerja\n"
        )
    if can_report(role, prof) or can_open_presensi:
        lines.extend([
            "<b>Sistem Presensi</b>",
            "/presensi — Menu Utama Presensi",
            ""
        ])
    if can_report(role, prof) or can_daftar_as_dean(role, prof) or can_daftar_as_lecturer(role, prof):
        lines.extend(
            [
                "<b>Daftar Pengguna</b>",
                "/daftar — Menu Daftar Pengguna",
                ""
            ]
        )
    if can_tag_all(role, prof):
        lines.extend(
            [
                "<b>Mention Grup</b>",
                "/tagall — Menu Mention & Broadcast",
                ""
            ]
        )
    if can_manage_agra(role, prof):
        lines.extend(
            [
                "<b>Manajemen Agra</b>",
                "/agra — Menu Manajemen Agra",
                "",
            ]
        )

    if role in (ROLE_OWNER, ROLE_ADMIN):
        lines.extend([
            "<b>Auto-reply (Trigger)</b>",
            "/trigger — Menu Auto-reply",
            ""
        ])
    if can_view_sensitive_logs(role, prof):
        lines.extend(
            [
                "<b>Audit & Log</b>",
                "/log — Ringkasan & Menu Log",
                ""
            ]
        )
    if can_approve_profile(role, prof):
        lines.extend(
            [
                "<b>Admin</b>",
                "/pending — Antrean ubah profil",
                "<code>/admin_data [id/username]</code> — Ubah profil user",
                "<i>Atau balas pesan user lalu</i> <code>/admin_data</code>",
                "",
            ]
        )
    if role == ROLE_OWNER:
        lines.extend(
            [
                "<b>Owner</b>",
                "<code>/setrole [role] @user123…</code> / reply",
                "<i>Role: admin · internal · bem · student · public</i>",
                "<code>/gencode [jumlah]</code> — Generate kode akses",
                "<code>/gencode_avail</code> — Cek kode belum diklaim",
                "<code>/broadcast [role] [text]</code> — Broadcast pesan dari bot",
                "<code>/owner_reset</code> — Reset semua user",
                "<code>/orreset_user [id/username]</code> — Reset satu user",
                "",
            ]
        )
    lines.append(" ")
    return "\n".join(lines)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    role = row["role"] if row else ROLE_STUDENT
    profile = profile_from_row(row) if row else {}
    await update.message.reply_text(help_for_role(role, profile))


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    requester_id = update.effective_user.id
    requester_row = await user_row(conn, db, requester_id)
    requester_role = requester_row["role"] if requester_row else ROLE_STUDENT

    parts = (update.message.text or "").split()
    target_id = requester_id
    is_target_lookup = False
    if len(parts) >= 2:
        if requester_role not in (ROLE_OWNER, ROLE_ADMIN):
            await update.message.reply_text(
                "Hanya admin/owner yang bisa cek profil user lain."
            )
            return
        token = parts[1].strip()
        if token.isdigit():
            if len(token) < 8:
                cur = await conn.execute("SELECT telegram_id FROM users ORDER BY created_at ASC, telegram_id ASC LIMIT 1 OFFSET ?", (int(token)-1,))
                rkr = await cur.fetchone()
                if not rkr:
                    await update.message.reply_text("User dengan No. ID tsb tidak ditemukan.")
                    return
                target_id = rkr["telegram_id"]
            else:
                target_id = int(token)
        else:
            ids = await db.find_ids_by_usernames(conn, [token])
            if not ids:
                await update.message.reply_text("User tidak ditemukan.")
                return
            target_id = ids[0]
        is_target_lookup = True

    row = await user_row(conn, db, target_id)
    profile = profile_from_row(row)
    agra = await db.agra_total(conn, target_id) if row else 0
    requester_prof = profile_from_row(row) if row else {}
    show_raw = can_view_sensitive_logs(requester_role, requester_prof) and not is_target_lookup
    
    cur = await conn.execute("SELECT created_at FROM users WHERE telegram_id = ?", (target_id,))
    rt = await cur.fetchone()
    if rt:
        ca = rt["created_at"]
        cur = await conn.execute("SELECT COUNT(*) AS n FROM users WHERE created_at < ? OR (created_at = ? AND telegram_id <= ?)", (ca, ca, target_id))
        rr = await cur.fetchone()
        reg_id = f"{(rr['n'] or 1):04d}"
    else:
        reg_id = "0000"

    text = format_profile_card(
        row,
        profile=profile,
        agra=agra,
        show_internal=show_raw,
        user_role=row["role"] if row else ROLE_STUDENT,
    )
    await update.message.reply_text(
        f"<b>No. ID</b>: <code>{reg_id}</code>\n\n{text}",
        disable_web_page_preview=True #hapus koma ke baris ini kalo pengen ada thumbnail di bawah
    )


def _format_birth_date(raw: str) -> str:
    raw = (raw or "").strip()
    if len(raw) != 6 or not raw.isdigit():
        return raw or "—"
    dd = raw[:2]
    mm = raw[2:4]
    yy = raw[4:]
    
    months = {
        "01": "Januari", "02": "Februari", "03": "Maret", "04": "April",
        "05": "Mei", "06": "Juni", "07": "Juli", "08": "Agustus",
        "09": "September", "10": "Oktober", "11": "November", "12": "Desember"
    }
    m_name = months.get(mm, mm)
    
    y = int(yy)
    if y >= 30:
        year = f"19{yy}"
    else:
        year = f"20{yy}"
        
    return f"{dd} {m_name} {year}"


async def cmd_profile_dtl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    requester_id = update.effective_user.id
    requester_row = await user_row(conn, db, requester_id)
    requester_role = requester_row["role"] if requester_row else ROLE_STUDENT

    parts = (update.message.text or "").split()
    target_id = requester_id
    if len(parts) >= 2:
        if requester_role not in (ROLE_OWNER, ROLE_ADMIN):
            await update.message.reply_text(
                "Hanya admin/owner yang bisa cek profil dtl user lain."
            )
            return
        token = parts[1].strip()
        if token.isdigit():
            if len(token) < 8:
                cur = await conn.execute("SELECT telegram_id FROM users ORDER BY created_at ASC, telegram_id ASC LIMIT 1 OFFSET ?", (int(token)-1,))
                rkr = await cur.fetchone()
                if not rkr:
                    await update.message.reply_text("User dengan No. ID tsb tidak ditemukan.")
                    return
                target_id = rkr["telegram_id"]
            else:
                target_id = int(token)
        else:
            ids = await db.find_ids_by_usernames(conn, [token])
            if not ids:
                await update.message.reply_text("User tidak ditemukan.")
                return
            target_id = ids[0]

    row = await user_row(conn, db, target_id)
    if not row:
        await update.message.reply_text("User tidak ditemukan.")
        return
    
    profile = profile_from_row(row)
    
    cur = await conn.execute("SELECT created_at FROM users WHERE telegram_id = ?", (target_id,))
    rt = await cur.fetchone()
    if rt:
        ca = rt["created_at"]
        cur = await conn.execute("SELECT COUNT(*) AS n FROM users WHERE created_at < ? OR (created_at = ? AND telegram_id <= ?)", (ca, ca, target_id))
        rr = await cur.fetchone()
        reg_id = f"{(rr['n'] or 1):04d}"
    else:
        reg_id = "0000"

    full_name = profile.get("full_name") or "—"
    muse = profile.get("muse") or "—"
    birth_date = _format_birth_date(profile.get("birth_date"))

    text = (
        f"<b>No. ID</b>: <code>{reg_id}</code>\n"
        f"<b>Role</b>: {role_display(row['role'])}\n"
        f"<b>Nama Lengkap</b>: {full_name}\n"
        f"<b>Muse</b>: {muse}\n"
        f"<b>Tanggal Lahir</b>: {birth_date}"
    )
    
    join_reason = profile.get("join_reason")
    if join_reason:
        text += f"\n<b>Alasan Bergabung</b>: {join_reason}"

    await update.message.reply_text(
        text,
        disable_web_page_preview=True
    )


async def cmd_lengkapi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
    profile = profile_from_row(row)
    role = row["role"]
    if _is_lengkapi_done(profile):
        await update.message.reply_text(
            "Data awal sudah dilengkapi. Untuk perubahan pakai /ubah."
        )
        return
    miss = missing_required_fields(profile, role)
    if not miss:
        await db.set_profile_partial(conn, uid, {LENGKAPI_DONE_KEY: True})
        if role == "internal":
            await update.message.reply_text(
                "Data awal sudah lengkap. Selanjutnya gunakan /ubah untuk perubahan.\n\n✨ Silakan buat kontrak kerja Anda dengan mengetik /kontrak."
            )
        elif role == "maba":
            if "maba_group" not in profile:
                await update.message.reply_text(
                    "Data awal sudah lengkap. Selanjutnya gunakan /ubah untuk perubahan.\n\n"
                    "Anda belum dimasukkan ke Kelompok Maba karena belum menukarkan Kode Akses (Gencode). "
                    "Silakan pantau Grup OSPEK untuk mendapatkan instruksi lebih lanjut."
                )
            else:
                from bot.settings import MABA_GROUP_GIDS, MABA_GROUP_NAMES
                mg = int(profile.get("maba_group", 1))
                link = "(Grup kelompok belum disetel oleh admin)"
                try:
                    if len(MABA_GROUP_GIDS) >= mg:
                        gid = MABA_GROUP_GIDS[mg - 1]
                        invite = await context.bot.create_chat_invite_link(
                            chat_id=gid, 
                            member_limit=1, 
                            name=f"Maba {uid}"
                        )
                        link = invite.invite_link
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Gagal membuat invite link Maba {uid} di lengkapi: {e}")
                    link = "(Gagal mendapatkan tautan grup. Pastikan bot adalah admin di grup kelompok.)"
                    
                await update.message.reply_text(
                    f"Data awal sudah lengkap. Selanjutnya gunakan /ubah untuk perubahan.\n\n✨ Anda dimasukkan ke Kelompok {MABA_GROUP_NAMES.get(mg, mg)}. Silakan klik link berikut untuk bergabung ke grup kelompok Anda:\n{link}"
                )
        else:
            await update.message.reply_text(
                "Data awal sudah lengkap. Selanjutnya gunakan /ubah untuk perubahan."
            )
        return
    target_fields_raw = miss + optional_fields_still_open(profile, role)
    target_fields = []
    seen = set()
    for f in target_fields_raw:
        if f.key not in seen:
            target_fields.append(f)
            seen.add(f.key)

    await update.message.reply_text(
        "Pilih data yang ingin diisi / diperbarui (langsung tersimpan):",
        reply_markup=_lengkapi_keyboard(target_fields),
    )


async def cmd_ubah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return

    role = row["role"]
    profile = profile_from_row(row)
    await update.message.reply_text(
        "Pilih data yang ingin <b>diajukan</b> perubahannya (butuh persetujuan admin):",
        reply_markup=_ubah_keyboard(fields_for_role(role, profile)),
    )


def _lengkapi_keyboard(fields) -> InlineKeyboardMarkup:
    rows = []
    for f in fields:
        if f.type == "multi_choice" and f.choices_key:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {f.label}",
                        callback_data=f"openlm:{f.key}"[:64],
                    )
                ]
            )
        elif f.type == "choice" and f.choices_key:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {f.label}",
                        callback_data=f"openlc:{f.key}"[:64],
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {f.label}",
                        callback_data=f"openlt:{f.key}"[:64],
                    )
                ]
            )
    rows.append([InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")])
    return InlineKeyboardMarkup(rows)


def _ubah_keyboard(fields) -> InlineKeyboardMarkup:
    rows = []
    for f in fields:
        if f.type == "multi_choice" and f.choices_key:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📝 {f.label} (bisa banyak)",
                        callback_data=f"openem:{f.key}"[:64],
                    )
                ]
            )
        elif f.type == "choice" and f.choices_key:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📝 {f.label}",
                        callback_data=f"openec:{f.key}"[:64],
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📝 {f.label}",
                        callback_data=f"openet:{f.key}"[:64],
                    )
                ]
            )
    rows.append([InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")])
    return InlineKeyboardMarkup(rows)


def _admin_profile_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for f in PROFILE_FIELDS:
        if f.key == "student_id": # baru
            continue # baru
        suf = (
            " (multi)"
            if f.type == "multi_choice"
            else (" (teks)" if f.type == "text" else "")
        )
        rows.append(
            [
                InlineKeyboardButton(
                    f.label + suf,
                    callback_data=f"adgo:{f.key}"[:64],
                )
            ]
        )
    rows.append([
        InlineKeyboardButton("Selesai", callback_data="adgo:__done__"[:64]),
        InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action")
    ])
    return InlineKeyboardMarkup(rows)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    data = q.data
    conn = _conn(context)
    db = _db(context)
    uid = q.from_user.id

    if data == "cancel_action":
        await q.answer("Aksi dibatalkan.")
        try:
            await q.edit_message_text("Aksi dibatalkan.")
        except Exception as e:
            log.warning("cancel_action edit error: %s", e)
        return

    if data.startswith("pub:"):
        await q.answer()
        action = data.split(":")[1]
        
        if action == "hubungi":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Seputar kemitraan dan sejenisnya.", callback_data="pub:medpart")],
                [InlineKeyboardButton("Menghubungi staf SDM.", callback_data="pub:hrd")],
                [InlineKeyboardButton("Menghubungi staf Akademik.", callback_data="pub:akademik")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="pub:back")]
            ])
            try:
                await q.edit_message_text("Pilih instansi yang ingin Anda hubungi:", reply_markup=keyboard)
            except Exception as e:
                log.warning("pub:hubungi edit error: %s", e)
            
        elif action == "back":
            row_u = await user_row(conn, db, q.from_user.id)
            profile_u = profile_from_row(row_u) if row_u else {}
            buttons = []
            if not _is_lengkapi_done(profile_u):
                buttons.append([InlineKeyboardButton("🎓 Daftar Akun Mahasiswa Baru", callback_data="maba:start")])
            
            buttons.extend([
                [InlineKeyboardButton("👤 Daftar Akun Publik", callback_data="openlt:full_name")],
                [InlineKeyboardButton("📦 Pakai Kode Akademik", callback_data="pub:kode")],
                [InlineKeyboardButton("📞 Hubungi Instansi", callback_data="pub:hubungi")],
                [InlineKeyboardButton("💬 Pertanyaan Lainnya", callback_data="pub:lainnya")]
            ])
            keyboard = InlineKeyboardMarkup(buttons)
            try:
                await q.edit_message_text("Selamat datang! Silakan pilih menu berikut:", reply_markup=keyboard)
            except Exception as e:
                log.warning("pub:back edit error: %s", e)

        elif action in ("medpart", "hrd", "akademik"):
            username = "@dhruvaekagrabot" if action == "medpart" else ("@HRDhruvabot" if action == "hrd" else "@acadhruvabot")
            try:
                await q.edit_message_text(f"Silakan menghubungi {username}, ketik /start untuk kembali.")
            except Exception as e:
                log.warning("pub:action edit error: %s", e)
        elif action == "lainnya":
            await q.edit_message_text("Silakan ketik pertanyaan Anda. Pesan Anda akan langsung diteruskan ke tim kami.")
        elif action == "kode":
            conn = _conn(context)
            db = _db(context)
            await db.set_onboarding_step(conn, q.from_user.id, "INPUT_CODE")
            await q.edit_message_text("Silakan ketikkan kode akses yang Anda terima dari pihak akademik (huruf besar):")
        return

    if data.startswith("maba:"):
        action = data.split(":")[1]
        conn = _conn(context)
        db = _db(context)
        
        if action == "start":
            await q.answer()
            await db.set_onboarding_step(conn, uid, "MABA_NAME")
            await q.edit_message_text("Pendaftaran Mahasiswa Baru.\nSilakan ketikkan **Nama Lengkap** Anda:", parse_mode="Markdown")
        elif action == "verify":
            # This is called when they click "Verifikasi Kembali" after following channels
            # We need to check channels here. But we need their chat info.
            # We can check channel status here.
            from bot.settings import MABA_CH_IDS, MABA_GROUP_LINK
            from bot.handlers.common import build_maba_verification_text
            
            text_verify, all_followed = await build_maba_verification_text(context, uid)
                    
            if not all_followed:
                await q.answer()
                await q.edit_message_text(
                    text_verify,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Verifikasi Kembali", callback_data="maba:verify")]]),
                    parse_mode="Markdown"
                )
                return
                
            # If all followed, set onboarding step to MABA_PROMO_WAIT
            await db.set_onboarding_step(conn, uid, "MABA_PROMO_WAIT")
            await q.answer()
            
            instruction_text = (
                "✅ Channel berhasil diverifikasi!\n\n"
                "**Langkah Terakhir:**\n"
                "Sebelum kamu mendapatkan link grup OSPEK, silakan lakukan minimal **1x promosi** (menyebar postingan OPSTUD ke minimal 1 LPM atau share di Telegram Story).\n\n"
                "Kirimkan buktinya ke sini dengan format:\n"
                "`/lpm <link_pesan>` atau `/story <link_story>`\n\n"
                "Jika sistem sudah membalas '*Link berhasil divalidasi*', klik tombol di bawah ini untuk mengambil link grup OSPEK-mu."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Ambil Link OSPEK", callback_data="maba:claim_ospek")]])
            await q.edit_message_text(instruction_text, reply_markup=kb, parse_mode="Markdown")
            
        elif action == "claim_ospek":
            from bot.database import ROLE_MABA
            from bot.settings import MABA_GROUP_LINK, PENDAFTAR_CH_ID
            from bot.handlers.common import user_row, profile_from_row

            promo_count = await db.count_valid_promos(conn, uid)
            if promo_count < 1:
                await q.answer("❌ Kamu belum melakukan promosi atau sistem masih memvalidasinya. Tunggu sampai ada notifikasi berhasil!", show_alert=True)
                return

            await q.answer()
            await db.set_role(conn, uid, ROLE_MABA)
            await db.set_onboarding_step(conn, uid, None)
            
            success_text = "✅ Berhasil! Persyaratan promo terpenuhi. Anda resmi terdaftar sebagai Mahasiswa Baru.\n\n"
            if MABA_GROUP_LINK:
                success_text += f"Silakan bergabung ke grup OSPEK melalui link berikut:\n{MABA_GROUP_LINK}\n\nKegiatan promosi dapat tetap dilanjutkan dengan mengirim format: `/lpm <link_pesan>` atau `/story <link_story>`\n\n (Hadiah *1 Agra* per 1 sebaran LPM dan *3 Agra* per 1 _post story_)"
            else:
                success_text += "Grup OSPEK belum diatur oleh admin. Silakan tunggu informasi selanjutnya."
                
            await q.edit_message_text(success_text, disable_web_page_preview=True, parse_mode="Markdown")
            
            if PENDAFTAR_CH_ID:
                try:
                    row_tmp = await user_row(conn, db, uid)
                    prof_tmp = profile_from_row(row_tmp)
                    name_tmp = prof_tmp.get("full_name", "Tanpa Nama")
                    reason_tmp = prof_tmp.get("join_reason", "-")
                    username_tmp = f"@{row_tmp['username']}" if row_tmp and row_tmp["username"] else "-"
                    msg_pendaftar = f"**Nama:** [{name_tmp}](tg://user?id={uid})\n**Username:** {username_tmp}\n**Alasan Bergabung:** {reason_tmp}\n**ID:** `{uid}`"
                    await context.bot.send_message(chat_id=PENDAFTAR_CH_ID, text=msg_pendaftar, parse_mode="Markdown")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Gagal mengirim info pendaftar ke {PENDAFTAR_CH_ID}: {e}")
            
        return

    if data.startswith("orreset:"):
        # Owner-only safety gate.
        if not is_owner(q.from_user.id):
            await q.answer("Tidak diizinkan.", show_alert=True)
            return

        parts = data.split(":")
        # Supported:
        # - orreset:act:<SCOPE>
        # - orreset:pick_user:<UID>
        # - orreset:pick_class:<CLASS_ID>
        # - orreset:do:<ACTION>
        # - orreset:do_user:<SCOPE>:<UID>
        # - orreset:cancel
        if len(parts) >= 2 and parts[1] == "cancel":
            context.user_data.pop(ORRESET_SCOPE_KEY, None)
            await q.edit_message_text("Dibatalkan.")
            return

        if len(parts) >= 3 and parts[1] == "back" and parts[2] == "root":
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Semua (tanpa users)",
                            callback_data="orreset:act:ALL"[:64],
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🧾 Presensi: semua",
                            callback_data="orreset:act:ATT_ALL"[:64],
                        ),
                        InlineKeyboardButton(
                            "🆔 Presensi: per id",
                            callback_data="orreset:act:ATT_SESSION"[:64],
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "💳 Agra: semua",
                            callback_data="orreset:act:AGRA_ALL"[:64],
                        ),
                        InlineKeyboardButton(
                            "👤 Agra: per user",
                            callback_data="orreset:act:AGRA_USER"[:64],
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🧩 Audit log: semua",
                            callback_data="orreset:act:AUD_ALL"[:64],
                        ),
                        InlineKeyboardButton(
                            "🧾 Requests: semua",
                            callback_data="orreset:act:REQ_ALL"[:64],
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Tugas: semua",
                            callback_data="orreset:act:TASK_ALL"[:64],
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🧼 Reset semua user (kecuali env)",
                            callback_data="orreset:act:USER_ALL_EXCEPT_ENV"[:64],
                        ),
                        InlineKeyboardButton(
                            "♻️ Reset semua data per user",
                            callback_data="orreset:act:USER_ALL"[:64],
                        ),
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="orreset:cancel"[:64])],
                ]
            )
            context.user_data.pop(ORRESET_SCOPE_KEY, None)
            await q.edit_message_text(
                "Menu reset data (owner). Pilih varian, lalu konfirmasi untuk menghapus data.",
                reply_markup=kb,
            )
            return

        if len(parts) >= 3 and parts[1] == "act":
            scope = parts[2]
            conn = _conn(context)
            db = _db(context)

            if scope == "USER_ALL":
                context.user_data.pop(ORRESET_SCOPE_KEY, None)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="orreset:back:root"[:64])]
                ])
                await q.edit_message_text(
                    "Untuk mereset semua data per user, gunakan perintah:\n<code>/orreset_user &lt;id_atau_username&gt;</code>",
                    reply_markup=kb,
                )
                return

            if scope == "AGRA_USER":
                context.user_data.pop(ORRESET_SCOPE_KEY, None)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="orreset:back:root"[:64])]
                ])
                await q.edit_message_text(
                    "Untuk mereset agra per user, gunakan perintah:\n<code>/orreset_agra &lt;id_atau_username&gt;</code>",
                    reply_markup=kb,
                )
                return

            if scope == "ATT_SESSION":
                context.user_data[ORRESET_SCOPE_KEY] = scope
                page = int(parts[3]) if len(parts) >= 4 else 0
                limit = 10
                offset = page * limit
                cur = await conn.execute(
                    f"""
                    SELECT
                        s.id,
                        s.class_id,
                        s.opened_at,
                        s.opened_by,
                        u.profile_json AS opener_profile_json,
                        u.first_name AS opener_first,
                        u.last_name AS opener_last
                    FROM attendance_sessions s
                    LEFT JOIN users u ON u.telegram_id = s.opened_by
                    ORDER BY s.id DESC
                    LIMIT {limit + 1} OFFSET {offset}
                    """
                )
                sessions = await cur.fetchall()
                if not sessions and page == 0:
                    await q.edit_message_text("Belum ada sesi presensi.")
                    return

                has_next = len(sessions) > limit
                sessions = sessions[:limit]

                kb: list[list[InlineKeyboardButton]] = []
                row: list[InlineKeyboardButton] = []
                for s in sessions:
                    cid = s["class_id"]
                    lab = cid
                    for item in CHOICES.get("classes", []):
                        if item.get("id") == cid:
                            lab = str(item.get("label", cid))
                            break
                    sid = int(s["id"])
                    text = f"#{sid} {lab}"[:35]
                    row.append(
                        InlineKeyboardButton(
                            text,
                            callback_data=f"orreset:pick_session:{sid}"[:64],
                        )
                    )
                    if len(row) == 2:
                        kb.append(row)
                        row = []
                if row:
                    kb.append(row)
                    
                nav_row = []
                if page > 0:
                    nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"orreset:act:ATT_SESSION:{page-1}"[:64]))
                if has_next:
                    nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"orreset:act:ATT_SESSION:{page+1}"[:64]))
                if nav_row:
                    kb.append(nav_row)

                kb.append(
                    [
                        InlineKeyboardButton("⬅️ Back", callback_data="orreset:back:root"[:64]),
                        InlineKeyboardButton("❌ Cancel", callback_data="orreset:cancel"[:64]),
                    ]
                )

                await q.edit_message_text(
                    f"Pilih sesi presensi untuk di-reset (Hal {page+1}):",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
                return

            if scope == "ATT_CLASS":
                context.user_data[ORRESET_SCOPE_KEY] = scope
                page = int(parts[3]) if len(parts) >= 4 else 0
                limit = 10
                offset = page * limit
                
                # Pilih matkul.
                all_classes = CHOICES.get("classes", [])
                has_next = len(all_classes) > offset + limit
                classes_page = all_classes[offset:offset + limit]

                kb = []
                row: list[InlineKeyboardButton] = []
                for item in classes_page:
                    cid = item.get("id", "")
                    lab = str(item.get("label", cid))
                    row.append(
                        InlineKeyboardButton(
                            lab[:30],
                            callback_data=f"orreset:pick_class:{cid}"[:64],
                        )
                    )
                    if len(row) == 2:
                        kb.append(row)
                        row = []
                if row:
                    kb.append(row)
                    
                nav_row = []
                if page > 0:
                    nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"orreset:act:ATT_CLASS:{page-1}"[:64]))
                if has_next:
                    nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"orreset:act:ATT_CLASS:{page+1}"[:64]))
                if nav_row:
                    kb.append(nav_row)

                kb.append(
                    [
                        InlineKeyboardButton("⬅️ Back", callback_data="orreset:back:root"[:64]),
                        InlineKeyboardButton("❌ Cancel", callback_data="orreset:cancel"[:64]),
                    ]
                )
                await q.edit_message_text(
                    f"Pilih matkul untuk reset presensi (Hal {page+1}):",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
                return

            # Non-user action: langsung konfirmasi.
            action_label = scope.replace("_", " ").title()
            detail = (
                "Ini akan menghapus data operasional dari database (users tidak ikut terhapus)."
            )
            if scope == "USER_ALL_EXCEPT_ENV":
                detail = (
                    "Ini akan reset profil & <code>onboarding_step</code> semua user "
                    "(kecuali OWNER/ADMIN dari .env), jadi bisa /lengkapi lagi. "
                    "Data <code>seen</code> tetap dipertahankan."
                )
            elif scope == "ACADEMIC_PERIOD":
                detail = (
                    "⚠️ <b>TINDAKAN BESAR!</b>\n"
                    "1. SKS semua Student/BEM akan 'dibekukan' (diakumulasi).\n"
                    "2. Role mereka akan di-reset ke <b>public</b> (harus daftar ulang).\n"
                    "3. Pilihan Matkul, UKM, Fakultas, Jurusan akan dikosongkan.\n"
                    "4. Seluruh data Agra & Presensi akan <b>DIPUTUSKAN/DIHAPUS</b>."
                )
            await q.edit_message_text(
                f"Konfirmasi reset: <b>{action_label}</b>?\n\n{detail}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ YA, HAPUS",
                                callback_data=f"orreset:do:{scope}"[:64],
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⬅️ Back",
                                callback_data="orreset:back:root"[:64],
                            ),
                            InlineKeyboardButton(
                                "❌ Cancel",
                                callback_data="orreset:cancel"[:64],
                            ),
                        ],
                    ]
                ),
            )
            return

        if len(parts) >= 3 and parts[1] == "pick_user":
            # scope disimpan di user_data
            scope = context.user_data.get(ORRESET_SCOPE_KEY)
            if not scope:
                await q.edit_message_text("Sesi reset tidak valid. Coba /owner_reset lagi.")
                return
            uid = int(parts[2])
            # Ambil nama untuk preview
            conn = _conn(context)
            cur = await conn.execute("SELECT role, username, first_name, last_name, profile_json FROM users WHERE telegram_id = ?", (uid,))
            r = await cur.fetchone()
            prof = json.loads(r["profile_json"] or "{}") if r else {}
            full_name = (
                prof.get("full_name")
                or (f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() if r else "")
                or (f"@{r['username']}" if r and r["username"] else None)
                or str(uid)
            )
            await q.edit_message_text(
                f"Konfirmasi reset <b>{scope.replace('_',' ').title()}</b> untuk user:\n• {full_name}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ YA, HAPUS",
                                callback_data=f"orreset:do_user:{scope}:{uid}"[:64],
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⬅️ Back",
                                callback_data="orreset:back:root"[:64],
                            ),
                            InlineKeyboardButton(
                                "❌ Cancel",
                                callback_data="orreset:cancel"[:64],
                            ),
                        ],
                    ]
                ),
            )
            return

        if len(parts) >= 3 and parts[1] == "pick_class":
            scope = context.user_data.get(ORRESET_SCOPE_KEY)
            if scope != "ATT_CLASS":
                await q.edit_message_text("Sesi reset tidak valid. Coba /owner_reset lagi.")
                return
            class_id = parts[2]
            class_lab = class_id
            for item in CHOICES.get("classes", []):
                if str(item.get("id")) == class_id:
                    class_lab = str(item.get("label", class_id))
                    break
            await q.edit_message_text(
                f"Konfirmasi reset <b>presensi</b> untuk matkul:\n• {class_lab} (<code>{class_id}</code>)\n\n"
                "Ini akan menghapus sesi + record presensi milik matkul tersebut.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ YA, HAPUS",
                                callback_data=f"orreset:do:{scope}:{class_id}"[:64],
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⬅️ Back",
                                callback_data="orreset:back:root"[:64],
                            ),
                            InlineKeyboardButton(
                                "❌ Cancel",
                                callback_data="orreset:cancel"[:64],
                            ),
                        ],
                    ]
                ),
            )
            return

        if len(parts) >= 3 and parts[1] == "pick_session":
            scope = context.user_data.get(ORRESET_SCOPE_KEY)
            if scope != "ATT_SESSION":
                await q.edit_message_text("Sesi reset tidak valid. Coba /owner_reset lagi.")
                return
            session_id = int(parts[2])

            conn = _conn(context)
            cur = await conn.execute(
                """
                SELECT
                    s.id,
                    s.class_id,
                    s.opened_by,
                    s.opened_at,
                    u.profile_json AS opener_profile_json,
                    u.first_name AS opener_first,
                    u.last_name AS opener_last,
                    u.username AS opener_username
                FROM attendance_sessions s
                LEFT JOIN users u ON u.telegram_id = s.opened_by
                WHERE s.id = ?
                """,
                (session_id,),
            )
            s = await cur.fetchone()
            if not s:
                await q.edit_message_text("Sesi tidak ditemukan.")
                return

            class_lab = s["class_id"]
            for item in CHOICES.get("classes", []):
                if item.get("id") == s["class_id"]:
                    class_lab = str(item.get("label", s["class_id"]))
                    break

            opener_name = None
            if s["opener_profile_json"]:
                try:
                    opener_json = json.loads(s["opener_profile_json"] or "{}")
                    opener_name = opener_json.get("full_name")
                except Exception:
                    opener_name = None
            if not opener_name:
                opener_name = (
                    f"{s['opener_first'] or ''} {s['opener_last'] or ''}".strip()
                    or (f"@{s['opener_username']}" if s["opener_username"] else None)
                    or str(s["opened_by"])
                )

            await q.edit_message_text(
                f"Konfirmasi reset presensi untuk sesi:\n• <code>#{session_id}</code> {class_lab}\n• oleh {opener_name}\n\n"
                "Ini akan menghapus sesi + semua record presensi pada sesi tersebut.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ YA, HAPUS",
                                callback_data=f"orreset:do:{scope}:{session_id}"[:64],
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⬅️ Back",
                                callback_data="orreset:back:root"[:64],
                            ),
                            InlineKeyboardButton(
                                "❌ Cancel",
                                callback_data="orreset:cancel"[:64],
                            ),
                        ],
                    ]
                ),
            )
            return

        if len(parts) >= 3 and parts[1] == "do":
            # Non-user do, or do with class_id (ATT_CLASS).
            conn = _conn(context)
            db = _db(context)
            scope = parts[2]
            result: object
            if scope in ("ATT_CLASS", "ATT_SESSION") and len(parts) >= 4:
                target_id = parts[3]
                if scope == "ATT_CLASS":
                    result = await db.reset_attendance_for_class(conn, target_id)
                else:
                    result = await db.reset_attendance_for_session(
                        conn, int(target_id)
                    )
            else:
                if scope == "ALL":
                    result = await db.reset_all_data_except_users(conn)
                elif scope == "ATT_ALL":
                    result = await db.reset_attendance_all(conn)
                elif scope == "AGRA_ALL":
                    result = await db.reset_agra_all(conn)
                elif scope == "USER_ALL_EXCEPT_ENV":
                    result = await db.reset_all_users_all_data_except_env(conn)
                elif scope == "REQ_ALL":
                    result = await db.reset_profile_change_requests_all(conn)
                elif scope == "TASK_ALL":
                    result = await db.reset_tasks_all(conn)
                elif scope == "AUD_ALL":
                    result = await db.reset_audit_log_all(conn)
                elif scope == "SEEN_ALL":
                    result = await db.reset_group_seen_users_all(conn)
                elif scope == "ACADEMIC_PERIOD":
                    result = await db.reset_academic_period(conn)
                else:
                    await q.edit_message_text("Scope reset tidak dikenal.")
                    return

            context.user_data.pop(ORRESET_SCOPE_KEY, None)
            if isinstance(result, dict):
                lines = [f"• {k}: <code>{v}</code>" for k, v in result.items()]
                await q.edit_message_text(
                    "<b>Reset selesai.</b>\n" + "\n".join(lines),
                )
            else:
                await q.edit_message_text(
                    f"<b>Reset selesai.</b>\n• count: <code>{result}</code>"
                )
            return

        if len(parts) >= 4 and parts[1] == "do_user":
            conn = _conn(context)
            db = _db(context)
            scope = parts[2]
            uid = int(parts[3])
            result: object
            if scope == "ATT_USER":
                result = await db.reset_attendance_for_user(conn, uid)
            elif scope == "AGRA_USER":
                result = await db.reset_agra_for_user(conn, uid)
            elif scope == "REQ_USER":
                result = await db.reset_profile_change_requests_for_user(conn, uid)
            elif scope == "AUD_USER":
                result = await db.reset_audit_log_for_user(conn, uid)
            elif scope == "SEEN_USER":
                result = await db.reset_group_seen_users_for_user(conn, uid)
            elif scope == "USER_ALL":
                result = await db.reset_user_all_data(conn, uid)
            else:
                await q.edit_message_text("Scope reset user tidak dikenal.")
                return

            context.user_data.pop(ORRESET_SCOPE_KEY, None)
            if isinstance(result, dict):
                lines = [f"• {k}: <code>{v}</code>" for k, v in result.items()]
                await q.edit_message_text(
                    "<b>Reset selesai.</b>\n" + "\n".join(lines),
                )
            else:
                await q.edit_message_text(
                    f"<b>Reset selesai.</b>\n• count: <code>{result}</code>"
                )
            return

        # Fallback: jika callback tidak match bentuk yang diharapkan.
        await q.answer("Opsi reset tidak dikenali.", show_alert=True)
        return

    if data.startswith("o:"):
        from . import attendance

        await attendance.cb_open_presensi(update, context)
        return
    if data.startswith("h:") or data.startswith("i:") or data.startswith("sh:"):
        from . import attendance

        await attendance.cb_attendance_action(update, context)
        return

    if (
        data.startswith("tb:") or data == "tgbuka" or 
        data.startswith("tsi:") or data.startswith("tdv:") or 
        data.startswith("tsv:") or data.startswith("tacc:") or 
        data.startswith("trej:")
    ):
        from . import tugas
        await tugas.cb_tugas(update, context)
        return

    conn = _conn(context)
    db = _db(context)
    uid = q.from_user.id

    if (
        data.startswith("adgo:")
        or data.startswith("adlc:")
        or data.startswith("admlc:")
        or data.startswith("admld:")
    ):
        row_ad = await user_row(conn, db, uid)
        if not row_ad or not can_report(row_ad["role"], profile_from_row(row_ad)):
            await q.answer("Tidak diizinkan.", show_alert=True)
            return

        if data.startswith("adgo:"):
            await q.answer()
            field_key = data.split(":", 1)[1]
            if field_key == "__done__":
                context.user_data.pop(ADMIN_TARGET_KEY, None)
                _multi_clear(context)
                await db.set_onboarding_step(conn, uid, None)
                await q.edit_message_text("Selesai mengedit data user.")
                return
            tid_target = context.user_data.get(ADMIN_TARGET_KEY)
            if not tid_target:
                await q.edit_message_text("Pilih user dulu: /admin_data <id/username>.")
                return
            trow = await user_row(conn, db, tid_target)
            if not trow:
                await q.edit_message_text("User tidak ditemukan.")
                return
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            if not fdef:
                await q.edit_message_text("Field tidak valid.")
                return
            tprof = profile_from_row(trow)
            if fdef.type == "text":
                await db.set_onboarding_step(conn, uid, f"ADMIN_TEXT_LC:{field_key}")
                await q.edit_message_text(
                    f"Kirim teks untuk <b>{fdef.label}</b> (user <code>{tid_target}</code>).",
                )
                return
            if fdef.type == "choice" and fdef.choices_key:
                opts = filtered_choice_items(fdef, tprof)
                if not opts:
                    opts = list(CHOICES.get(fdef.choices_key, []))
                if not opts:
                    await q.edit_message_text("Tidak ada opsi.")
                    return
                await db.set_onboarding_step(conn, uid, f"PICK_AD_LC:{field_key}")
                kb = keyboard_for_choices(
                    field_key,
                    fdef.choices_key,
                    prefix="adlc",
                    options=opts,
                )
                await q.edit_message_text(
                    f"Pilih <b>{fdef.label}</b> untuk <code>{tid_target}</code>:",
                    reply_markup=kb,
                )
                return
            if fdef.type == "multi_choice" and fdef.choices_key:
                _multi_init(context, field_key, "ad", tprof)
                sel = context.user_data[MULTI_UD_KEY]["ids"]
                opts = filtered_choice_items(fdef, tprof)
                kb = keyboard_for_multi_choices(
                    field_key,
                    fdef.choices_key,
                    sel,
                    toggle_prefix="admlc",
                    done_prefix="admld",
                    options=opts,
                )
                await db.set_onboarding_step(conn, uid, f"MULTI_AD_LC:{field_key}")
                await q.edit_message_text(
                    f"Pilih <b>{fdef.label}</b> (multi) untuk <code>{tid_target}</code>.",
                    reply_markup=kb,
                )
                return
            await q.edit_message_text("Tipe field tidak didukung.")
            return

        if data.startswith("adlc:"):
            await q.answer()
            _, field_key, choice_id = data.split(":", 2)
            tid_target = context.user_data.get(ADMIN_TARGET_KEY)
            step_row = await user_row(conn, db, uid)
            step = (step_row["onboarding_step"] or "") if step_row else ""
            if not step.startswith("PICK_AD_LC:") or step.split(":", 1)[1] != field_key:
                await q.edit_message_text("Sesi habis.")
                return
            if not tid_target:
                await q.edit_message_text("Target tidak ada.")
                return
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            
            update_dict = {field_key: choice_id}
            if field_key == "position_detail":
                pos_id = None
                for item in CHOICES.get("position_details", []):
                    if item.get("id") == choice_id:
                        pos_id = item.get("position")
                        break
                if pos_id:
                    update_dict["position"] = pos_id
            
            await db.set_profile_partial(conn, tid_target, update_dict)
            await _revalidate_filtered_choice_fields(conn, db, tid_target)
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(
                conn, uid, "admin_profile_set", f"target={tid_target} key={field_key}"
            )
            lab = fdef.label if fdef else field_key
            await q.edit_message_text(f"✅ {lab} untuk <code>{tid_target}</code> disimpan.")
            return

        if data.startswith("admlc:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                await q.answer()
                return
            _, field_key, choice_id = parts
            await q.answer()
            tid_target = context.user_data.get(ADMIN_TARGET_KEY)
            step_row = await user_row(conn, db, uid)
            step = (step_row["onboarding_step"] or "") if step_row else ""
            if not step.startswith("MULTI_AD_LC:") or step.split(":", 1)[1] != field_key:
                await q.edit_message_text("Sesi habis.")
                return
            if not tid_target:
                await q.edit_message_text("Target tidak ada.")
                return
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            
            m = context.user_data.get(MULTI_UD_KEY)
            if not m or m.get("field") != field_key or m.get("flow") != "ad":
                await q.edit_message_text("Sesi habis.")
                return
            ids_set: set[str] = m["ids"]
            if choice_id in ids_set:
                ids_set.discard(choice_id)
            else:
                ids_set.add(choice_id)
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            if not fdef or not fdef.choices_key:
                return
            trow = await user_row(conn, db, tid_target)
            tprof_now = profile_from_row(trow) if trow else {}
            opts = filtered_choice_items(fdef, tprof_now)
            kb = keyboard_for_multi_choices(
                field_key,
                fdef.choices_key,
                ids_set,
                toggle_prefix="admlc",
                done_prefix="admld",
                options=opts,
            )
            await q.edit_message_text(
                f"Pilih <b>{fdef.label}</b> (multi) untuk <code>{tid_target}</code>.",
                reply_markup=kb,
            )
            return

        if data.startswith("admld:"):
            field_key = data.split(":", 1)[1]
            tid_target = context.user_data.get(ADMIN_TARGET_KEY)
            step_row = await user_row(conn, db, uid)
            step = (step_row["onboarding_step"] or "") if step_row else ""
            m = context.user_data.get(MULTI_UD_KEY)
            if (
                not step.startswith("MULTI_AD_LC:")
                or step.split(":", 1)[1] != field_key
                or not m
                or m.get("flow") != "ad"
                or m.get("field") != field_key
            ):
                await q.answer()
                await q.edit_message_text("Sesi habis.")
                return
            if not tid_target:
                await q.answer()
                await q.edit_message_text("Target tidak ada.")
                return
            fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
            ids_list = sorted(m["ids"])
            if fdef and fdef.required and not ids_list:
                await q.answer("Pilih minimal satu.", show_alert=True)
                return
            await q.answer()
            await db.set_profile_partial(conn, tid_target, {field_key: ids_list})
            await _revalidate_filtered_choice_fields(conn, db, tid_target)
            _multi_clear(context)
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(
                conn,
                uid,
                "admin_profile_set",
                f"target={tid_target} key={field_key} multi",
            )
            lab = fdef.label if fdef else field_key
            await q.edit_message_text(
                f"✅ {lab} ({len(ids_list)} pilihan) untuk <code>{tid_target}</code> disimpan."
            )
            return

    if data.startswith("openlc:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or fdef.type != "choice" or not fdef.choices_key:
            await q.edit_message_text("Field tidak valid.")
            return
        row_u = await user_row(conn, db, uid)
        profile_u = profile_from_row(row_u) if row_u else {}
        if _is_lengkapi_done(profile_u):
            await q.edit_message_text("/lengkapi hanya untuk isi awal. Pakai /ubah.")
            return
        opts = filtered_choice_items(fdef, profile_u)
        if not opts:
            hint = (
                f"Pilih <b>{fdef.filter_by_field}</b> dulu di /lengkapi."
                if fdef.filter_by_field
                else "Tidak ada opsi."
            )
            await q.edit_message_text(hint)
            return
        await q.edit_message_text(
            f"Pilih <b>{fdef.label}</b>:",
            reply_markup=keyboard_for_choices(
                field_key,
                fdef.choices_key,
                prefix="lc",
                options=opts,
            ),
        )
        await db.set_onboarding_step(conn, uid, f"PICK_LC:{field_key}")
        return

    if data.startswith("openlt:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef:
            await q.edit_message_text("Field tidak valid.")
            return
        row_u = await user_row(conn, db, uid)
        profile_u = profile_from_row(row_u) if row_u else {}
        if _is_lengkapi_done(profile_u):
            try:
                await q.edit_message_text("/lengkapi hanya untuk isi awal. Pakai /ubah.")
            except Exception:
                pass
            return
        await db.set_onboarding_step(conn, uid, f"TEXT_LC:{field_key}")
        try:
            await q.edit_message_text(
                f"Kirim pesan teks untuk <b>{fdef.label}</b> (lengkapi).",
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("openlt edit_message_text error: %s", e)
        return

    if data.startswith("openec:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or fdef.type != "choice" or not fdef.choices_key:
            await q.edit_message_text("Field tidak valid.")
            return
        row_u = await user_row(conn, db, uid)
        profile_u = profile_from_row(row_u) if row_u else {}
        opts = filtered_choice_items(fdef, profile_u)
        if not opts:
            hint = (
                f"Set <b>{fdef.filter_by_field}</b> dulu (lengkapi profil), atau tidak ada jurusan untuk fakultas ini."
                if fdef.filter_by_field
                else "Tidak ada opsi."
            )
            await q.edit_message_text(hint)
            return
        await q.edit_message_text(
            f"Pilih nilai baru <b>{fdef.label}</b> (akan diajukan):",
            reply_markup=keyboard_for_choices(
                field_key,
                fdef.choices_key,
                prefix="ec",
                options=opts,
            ),
        )
        await db.set_onboarding_step(conn, uid, f"PICK_EC:{field_key}")
        return

    if data.startswith("openet:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef:
            await q.edit_message_text("Field tidak valid.")
            return
        await db.set_onboarding_step(conn, uid, f"TEXT_EC:{field_key}")
        await q.edit_message_text(
            f"Kirim teks baru untuk <b>{fdef.label}</b> (akan diajukan ke admin).",
        )
        return

    if data.startswith("openlm:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or fdef.type != "multi_choice" or not fdef.choices_key:
            await q.edit_message_text("Field tidak valid.")
            return
        row = await user_row(conn, db, uid)
        profile = profile_from_row(row) if row else {}
        if _is_lengkapi_done(profile):
            await q.edit_message_text("/lengkapi hanya untuk isi awal. Pakai /ubah.")
            return
        _multi_init(context, field_key, "lc", profile)
        sel = context.user_data[MULTI_UD_KEY]["ids"]
        opts = filtered_choice_items(fdef, profile)
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            sel,
            toggle_prefix="mlc",
            done_prefix="mld",
            options=opts,
        )
        await db.set_onboarding_step(conn, uid, f"MULTI_LC:{field_key}")
        await q.edit_message_text(
            f"Pilih satu atau lebih <b>{fdef.label}</b> (ketuk untuk centang, lalu <b>Selesai</b>).",
            reply_markup=kb,
        )
        return

    if data.startswith("openem:"):
        await q.answer()
        _multi_clear(context)
        field_key = data.split(":", 1)[1]
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or fdef.type != "multi_choice" or not fdef.choices_key:
            await q.edit_message_text("Field tidak valid.")
            return
        row = await user_row(conn, db, uid)
        profile = profile_from_row(row) if row else {}
        _multi_init(context, field_key, "ec", profile)
        sel = context.user_data[MULTI_UD_KEY]["ids"]
        opts = filtered_choice_items(fdef, profile)
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            sel,
            toggle_prefix="mec",
            done_prefix="med",
            options=opts,
        )
        await db.set_onboarding_step(conn, uid, f"MULTI_EC:{field_key}")
        await q.edit_message_text(
            f"Pilih nilai baru <b>{fdef.label}</b>. Ajuan dikirim setelah <b>Selesai</b>.",
            reply_markup=kb,
        )
        return

    if data.startswith("mlc:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            await q.answer()
            return
        _, field_key, choice_id = parts
        await q.answer()
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        if not step.startswith("MULTI_LC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /lengkapi lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        m = context.user_data.get(MULTI_UD_KEY)
        if not m or m.get("field") != field_key or m.get("flow") != "lc":
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /lengkapi lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        ids: set[str] = m["ids"]
        if choice_id in ids:
            ids.discard(choice_id)
        else:
            ids.add(choice_id)
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or not fdef.choices_key:
            return
        row_now = await user_row(conn, db, uid)
        prof_now = profile_from_row(row_now) if row_now else {}
        opts = filtered_choice_items(fdef, prof_now)
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            ids,
            toggle_prefix="mlc",
            done_prefix="mld",
            options=opts,
        )
        await q.edit_message_text(
            f"Pilih satu atau lebih <b>{fdef.label}</b> (ketuk untuk centang, lalu <b>Selesai</b>).",
            reply_markup=kb,
        )
        return

    if data.startswith("mld:"):
        field_key = data.split(":", 1)[1]
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        profile_now = profile_from_row(step_row) if step_row else {}
        m = context.user_data.get(MULTI_UD_KEY)
        if _is_lengkapi_done(profile_now):
            await q.answer()
            await q.edit_message_text(
                "/lengkapi sudah ditutup. Gunakan /ubah.", reply_markup=None
            )
            _multi_clear(context)
            return
        if not step.startswith("MULTI_LC:") or step.split(":", 1)[1] != field_key:
            await q.answer()
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /lengkapi lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        if not m or m.get("field") != field_key or m.get("flow") != "lc":
            await q.answer()
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /lengkapi lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        ids_list = sorted(m["ids"])
        if fdef and fdef.required and not ids_list:
            await q.answer("Pilih minimal satu opsi.", show_alert=True)
            return
        await q.answer()
        await db.set_profile_partial(conn, uid, {field_key: ids_list})
        await _mark_lengkapi_done_if_complete(conn, db, uid)
        
        from .common import award_lengkapi_agra
        await award_lengkapi_agra(conn, db, uid, field_key, profile_now, context, q.message.chat_id)
        
        _multi_clear(context)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        updated_row = await user_row(conn, db, uid)
        updated_profile = profile_from_row(updated_row) if updated_row else {}
        sks_suffix = ""
        if updated_row and updated_row["role"] in (ROLE_STUDENT, ROLE_BEM):
            sks_suffix = f"\nTotal SKS saat ini: {updated_profile.get('total_sks', 0)}"
        await q.edit_message_text(
            f"✅ {lab} disimpan ({len(ids_list)} pilihan).{sks_suffix}",
            reply_markup=None,
        )
        return

    if data.startswith("mec:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            await q.answer()
            return
        _, field_key, choice_id = parts
        await q.answer()
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        if not step.startswith("MULTI_EC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /ubah lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        m = context.user_data.get(MULTI_UD_KEY)
        if not m or m.get("field") != field_key or m.get("flow") != "ec":
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /ubah lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        ids = m["ids"]
        if choice_id in ids:
            ids.discard(choice_id)
        else:
            ids.add(choice_id)
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        if not fdef or not fdef.choices_key:
            return
        row_now = await user_row(conn, db, uid)
        prof_now = profile_from_row(row_now) if row_now else {}
        opts = filtered_choice_items(fdef, prof_now)
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            ids,
            toggle_prefix="mec",
            done_prefix="med",
            options=opts,
        )
        await q.edit_message_text(
            f"Pilih nilai baru <b>{fdef.label}</b> (bisa banyak). Ajuan dikirim setelah <b>Selesai</b>.",
            reply_markup=kb,
        )
        return

    if data.startswith("med:"):
        field_key = data.split(":", 1)[1]
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        m = context.user_data.get(MULTI_UD_KEY)
        if not step.startswith("MULTI_EC:") or step.split(":", 1)[1] != field_key:
            await q.answer()
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /ubah lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        if not m or m.get("field") != field_key or m.get("flow") != "ec":
            await q.answer()
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /ubah lagi.", reply_markup=None
            )
            _multi_clear(context)
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        ids_list = sorted(m["ids"])
        if fdef and fdef.required and not ids_list:
            await q.answer("Pilih minimal satu opsi.", show_alert=True)
            return
        await q.answer()
        
        prof = profile_from_row(step_row) if step_row else {}
        from bot.handlers.common import normalize_multi_choice_value
        current_ids = sorted(normalize_multi_choice_value(prof.get(field_key)))
        if current_ids == ids_list:
            await q.edit_message_text("Tidak ada perubahan yang diajukan.", reply_markup=None)
            _multi_clear(context)
            await db.set_onboarding_step(conn, uid, None)
            return

        if step_row and step_row["role"] in ("owner", "admin"):
            await db.set_profile_partial(conn, uid, {field_key: ids_list})
            _multi_clear(context)
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(conn, uid, "profile_direct_update", field_key)
            lab = fdef.label if fdef else field_key
            await q.edit_message_text(f"✅ {lab} disimpan (auto-approved).", reply_markup=None)
            return

        rid = await db.add_profile_request(conn, uid, {field_key: ids_list})
        _multi_clear(context)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await q.edit_message_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin.",
            reply_markup=None,
        )
        await _notify_moderators_profile(
            context, db, conn, rid, uid, {field_key: ids_list}
        )
        return

    if data.startswith("lc:"):
        await q.answer()
        _, field_key, choice_id = data.split(":", 2)
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        profile_now = profile_from_row(step_row) if step_row else {}
        if _is_lengkapi_done(profile_now):
            await q.edit_message_text(
                "/lengkapi sudah ditutup. Gunakan /ubah.", reply_markup=None
            )
            return
        if not step.startswith("PICK_LC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /lengkapi lagi.", reply_markup=None
            )
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        prof_before = profile_from_row(step_row) if step_row else {}
        if fdef and fdef.filter_by_field and not is_choice_allowed_for_profile(
            fdef, prof_before, choice_id
        ):
            await q.edit_message_text(
                "Pilihan tidak cocok dengan data profil (mis. fakultas). Buka /lengkapi lagi.",
                reply_markup=None,
            )
            return
        update_dict = {field_key: choice_id}
        if field_key == "position_detail":
            pos_id = None
            for item in CHOICES.get("position_details", []):
                if item.get("id") == choice_id:
                    pos_id = item.get("position")
                    break
            if pos_id:
                update_dict["position"] = pos_id
        
        await db.set_profile_partial(conn, uid, update_dict)
        await _mark_lengkapi_done_if_complete(conn, db, uid)
        
        from .common import award_lengkapi_agra
        await award_lengkapi_agra(conn, db, uid, field_key, prof_before, context, q.message.chat_id)
        
        await _revalidate_filtered_choice_fields(conn, db, uid)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        updated_row = await user_row(conn, db, uid)
        updated_profile = profile_from_row(updated_row) if updated_row else {}
        sks_suffix = ""
        if updated_row and updated_row["role"] in (ROLE_STUDENT, ROLE_BEM):
            sks_suffix = f"\nTotal SKS saat ini: {updated_profile.get('total_sks', 0)}"
        await q.edit_message_text(
            f"✅ {lab} disimpan.{sks_suffix}", reply_markup=None
        )
        return

    if data.startswith("ec:"):
        await q.answer()
        _, field_key, choice_id = data.split(":", 2)
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        if not step.startswith("PICK_EC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text(
                "Sesi kedaluwarsa. Buka /ubah lagi.", reply_markup=None
            )
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        prof_before = profile_from_row(step_row) if step_row else {}
        if fdef and fdef.filter_by_field and not is_choice_allowed_for_profile(
            fdef, prof_before, choice_id
        ):
            await q.edit_message_text(
                "Pilihan tidak valid untuk fakultas kamu saat ini. Perbarui fakultas dulu jika perlu.",
                reply_markup=None,
            )
            return
        req_dict = {field_key: choice_id}
        if field_key == "position_detail":
            pos_id = None
            for item in CHOICES.get("position_details", []):
                if item.get("id") == choice_id:
                    pos_id = item.get("position")
                    break
            if pos_id:
                req_dict["position"] = pos_id

        prof = profile_from_row(step_row) if step_row else {}
        if prof.get(field_key) == choice_id:
            await q.edit_message_text("Tidak ada perubahan yang diajukan.", reply_markup=None)
            await db.set_onboarding_step(conn, uid, None)
            return

        if step_row and step_row["role"] in ("owner", "admin"):
            await db.set_profile_partial(conn, uid, req_dict)
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(conn, uid, "profile_direct_update", field_key)
            lab = fdef.label if fdef else field_key
            await q.edit_message_text(f"✅ {lab} disimpan (auto-approved).", reply_markup=None)
            return

        rid = await db.add_profile_request(conn, uid, req_dict)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await q.edit_message_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin.",
            reply_markup=None,
        )
        await _notify_moderators_profile(context, db, conn, rid, uid, {field_key: choice_id})
        return

    if data.startswith("a:"):
        await q.answer()
        parts = data.split(":")
        if len(parts) != 3:
            return
        _, rid_s, dec = parts
        rid_int = int(rid_s)
        row_u = await user_row(conn, db, uid)
        if not row_u or not can_approve_profile(row_u["role"], profile_from_row(row_u)):
            await q.edit_message_text("Tidak diizinkan.")
            return
        fallback_base = q.message.text or f"Pengajuan #{rid_s}"
        ok, tid, proposed = await db.resolve_profile_request(
            conn, rid_int, approve=(dec == "1"), decided_by=uid
        )
        if not ok:
            req = await db.get_profile_request(conn, rid_int)
            if not req:
                await q.edit_message_text("Permintaan tidak tersedia.")
                return
            if req["status"] in ("approved", "rejected"):
                decided_by_row = await user_row(conn, db, int(req["decided_by"] or 0))
                decided_by_name = _display_name_from_row(decided_by_row)
                final_status = "disetujui" if req["status"] == "approved" else "ditolak"
                broadcast_ok = await _broadcast_profile_request_status(
                    context,
                    db,
                    conn,
                    rid_int,
                    status=final_status,
                    decided_by_name=decided_by_name,
                    fallback_base_text=fallback_base,
                )
                if not broadcast_ok:
                    original_text = q.message.text or f"Pengajuan #{rid_s}"
                    await q.edit_message_text(
                        _profile_request_status_text(
                            original_text,
                            status=final_status,
                            decided_by_name=decided_by_name,
                        )
                    )
                return
            await q.edit_message_text("Permintaan tidak tersedia.")
            return
        await db.add_audit(
            conn,
            uid,
            "profile_request_decided",
            f"id={rid_s} approve={dec} target={tid}",
        )
        status = "disetujui" if dec == "1" else "ditolak"
        decided_by_name = _display_name_from_row(row_u)
        broadcast_ok = await _broadcast_profile_request_status(
            context,
            db,
            conn,
            rid_int,
            status=status,
            decided_by_name=decided_by_name,
            fallback_base_text=fallback_base,
        )
        if not broadcast_ok:
            original_text = q.message.text or f"Pengajuan #{rid_s}"
            await q.edit_message_text(
                _profile_request_status_text(
                    original_text,
                    status=status,
                    decided_by_name=decided_by_name,
                )
            )
        if tid and dec == "1":
            await _revalidate_filtered_choice_fields(conn, db, tid)
        if tid:
            try:
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"Perubahan profil kamu <b>{status}</b>.",
                )
            except Exception as e:
                log.warning("notify user fail: %s", e)
        if tid and dec == "1":
            try:
                nu = await user_row(conn, db, tid)
                prof_nu = profile_from_row(nu) if nu else {}
                if nu and "faculty" in proposed and not prof_nu.get("major"):
                    await context.bot.send_message(
                        chat_id=tid,
                        text=(
                            "Jurusan telah dikosongkan secara otomatis karena baru saja mengganti fakultas. "
                            "Silakan lengkapi profil menggunakan /lengkapi atau /ubah."
                        ),
                    )
            except Exception as e:
                log.warning("notify dependent clear: %s", e)
        return


async def _notify_moderators_profile(
    context, db, conn, request_id: int, proposer_id: int, proposed: dict
) -> None:
    mods = await moderator_chat_ids(db, conn)
    proposer = await user_row(conn, db, proposer_id)
    un = proposer["username"] if proposer else ""
    current_profile = profile_from_row(proposer) if proposer else {}
    before_subset = {k: current_profile.get(k) for k in proposed.keys()}
    before_preview = json.dumps(before_subset, ensure_ascii=False)[:200]
    preview = json.dumps(proposed, ensure_ascii=False)[:200]
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Setujui", callback_data=f"a:{request_id}:1"[:32]
                ),
                InlineKeyboardButton(
                    "❌ Tolak", callback_data=f"a:{request_id}:0"[:32]
                ),
            ]
        ]
    )
    text = (
        f"📩 Pengajuan ubah profil #{request_id}\n"
        f"Dari: <code>{proposer_id}</code> @{un}\n"
        f"Data awal: <code>{html.escape(before_preview)}</code>\n"
        f"Usulan: <code>{html.escape(preview)}</code>"
    )
    await db.set_profile_request_moderator_prompt(conn, request_id, text)
    for mid in mods:
        if mid == proposer_id:
            continue
        try:
            sent = await context.bot.send_message(
                chat_id=mid, text=text, reply_markup=kb
            )
            await db.register_profile_request_mod_message(
                conn, request_id, mid, sent.message_id
            )
        except Exception as e:
            log.warning("mod notify %s: %s", mid, e)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not can_manage_agra(row["role"], profile_from_row(row)):
        await update.message.reply_text("Kamu tidak punya akses menambah Agra.")
        return

    parsed = parse_add_command(update.message)
    if not parsed:
        await update.message.reply_text(
            "Format: <code>/add &lt;angka&gt; @user … | &lt;deskripsi&gt;</code> atau reply pesan user lalu "
            "<code>/add &lt;angka&gt; | &lt;deskripsi&gt;</code>",
        )
        return

    extra_ids = await db.find_ids_by_usernames(conn, parsed.mention_usernames)
    targets = set(parsed.target_ids) | set(extra_ids)
    
    if parsed.target_role:
        from bot.database import ROLES_ORDER
        if parsed.target_role in ROLES_ORDER:
            cur = await conn.execute("SELECT telegram_id FROM users WHERE role = ?", (parsed.target_role,))
            role_users = await cur.fetchall()
            targets |= {r["telegram_id"] for r in role_users}
        else:
            await update.message.reply_text(f"Role '{parsed.target_role}' tidak valid. Role yang tersedia: {', '.join(ROLES_ORDER)}")
            return

    if not targets:
        await update.message.reply_text(
            "Sebutkan user dengan @mention, text mention, role yang valid (e.g. internal, student), atau reply pesannya."
        )
        return

    chat_id = update.message.chat_id
    mid = update.message.message_id
    lines = []
    for tid in sorted(targets):
        urow = await user_row(conn, db, tid)
        if not urow:
            uname = "(tanpa username)"
            try:
                chat = await context.bot.get_chat(tid)
                if chat.username:
                    uname = f"@{chat.username}"
            except Exception:
                pass
            lines.append(f"• {uname} belum /start — dilewati.")
            continue
        await db.add_agra(
            conn,
            target_id=tid,
            actor_id=actor,
            amount=parsed.amount,
            description=parsed.description,
            chat_id=chat_id,
            message_id=mid,
        )
        new_total = await db.agra_total(conn, tid)
        prof = profile_from_row(urow)
        full_name = html.escape(str(
            prof.get("full_name")
            or f"{urow['first_name'] or ''} {urow['last_name'] or ''}".strip()
            or (f"@{urow['username']}" if urow["username"] else str(tid))
        ))
        lines.append(f"→ {full_name}") # (total {new_total})
        try:
            desc_text = f"\nKeterangan: {html.escape(str(parsed.description))}" if parsed.description else ""
            await context.bot.send_message(
                chat_id=tid,
                text=f"Kamu menerima <b>{parsed.amount}</b> Agra.{desc_text}",
            )
        except Exception:
            pass

    await db.add_audit(conn, actor, "agra_add", f"targets={targets} amount={parsed.amount}")
    summary = "\n".join(lines)
    await update.message.reply_text(
        f"✅ <b>{parsed.amount} Agra</b> berhasil dicatat.\n\nPenerima:\n{summary}",
    )


async def cmd_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return

    parsed = parse_add_command(update.message)
    if not parsed:
        await update.message.reply_text(
            "Format: <code>/transfer &lt;angka&gt; @user … | &lt;deskripsi&gt;</code>",
        )
        return

    if parsed.amount <= 0:
        await update.message.reply_text("Nominal transfer harus lebih besar dari 0.")
        return

    extra_ids = await db.find_ids_by_usernames(conn, parsed.mention_usernames)
    targets = set(parsed.target_ids) | set(extra_ids)
    if not targets:
        await update.message.reply_text("Sebutkan user dengan @mention atau text mention.")
        return
        
    if actor in targets:
        await update.message.reply_text("Tidak bisa transfer ke diri sendiri.")
        return

    total_cost = parsed.amount * len(targets)
    chat_id = update.message.chat_id
    mid = update.message.message_id
    
    # ATOMIC DEDUCTION (Fix TOCTOU Race Condition)
    deducted = await db.deduct_agra_if_sufficient(
        conn,
        target_id=actor,
        actor_id=actor,
        amount=total_cost,
        description=f"Transfer masal ke {len(targets)} user",
        chat_id=chat_id,
        message_id=mid,
    )
    if not deducted:
        current_agra = await db.agra_total(conn, actor)
        await update.message.reply_text(f"Agra tidak cukup (atau transaksi bentrok). Saldo kamu: {current_agra}, butuh: {total_cost}.")
        return

    lines = []
    success_count = 0
    
    actor_prof = profile_from_row(row)
    actor_full_name = html.escape(str(actor_prof.get("full_name") or f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or (f"@{row['username']}" if row["username"] else "User")))
    
    for tid in sorted(targets):
        urow = await user_row(conn, db, tid)
        if not urow:
            lines.append(f"• User ID <code>{tid}</code> belum /start — dilewati.")
            # Refund partial if user not found (since we deducted in bulk)
            await db.add_agra(
                conn, target_id=actor, actor_id=actor, amount=parsed.amount,
                description=f"Refund transfer gagal ke {tid}", chat_id=chat_id, message_id=mid
            )
            continue
            
        prof = profile_from_row(urow)
        target_full_name = html.escape(str(prof.get("full_name") or f"{urow['first_name'] or ''} {urow['last_name'] or ''}".strip() or (f"@{urow['username']}" if urow["username"] else "User")))
            
        desc = html.escape(str(parsed.description or "Transfer Agra"))
        
        # Add to target
        await db.add_agra(
            conn,
            target_id=tid,
            actor_id=actor,
            amount=parsed.amount,
            description=f"Transfer dari {actor_full_name}: {desc}",
            chat_id=chat_id,
            message_id=mid,
        )
        
        lines.append(f"→ {target_full_name}")
        success_count += 1
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"Kamu menerima transfer <b>{parsed.amount}</b> Agra.\nKeterangan: {desc}",
            )
        except Exception:
            pass

    if success_count > 0:
        await db.add_audit(conn, actor, "agra_transfer", f"targets={targets} amount={parsed.amount}")
        
    summary = "\n".join(lines)
    await update.message.reply_text(
        f"✅ Transfer <b>{parsed.amount} Agra</b> berhasil ke {success_count} orang.\n\nPenerima:\n{summary}",
    )


async def cmd_agralog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    uid = update.effective_user.id
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start dulu.")
        return
        
    is_from_log_cmd = getattr(context, "is_from_log_cmd", False)
    is_global = False
    target_uid = uid
    title_suffix = "Kamu"
    
    if is_from_log_cmd:
        if row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
            await update.message.reply_text("Hanya admin/owner yang bisa melihat log Agra global/spesifik.")
            return
            
        if not context.args:
            is_global = True
        elif context.args[0].startswith("@"):
            username = context.args[0].lstrip("@")
            target_ids = await db.find_ids_by_usernames(conn, [username])
            if not target_ids:
                await update.message.reply_text(f"User {html.escape(str(context.args[0]))} tidak ditemukan.")
                return
            target_uid = target_ids[0]
            title_suffix = context.args[0]
        elif context.args[0].isdigit():
            target_uid = int(context.args[0])
            title_suffix = f"ID {target_uid}"
        else:
            await update.message.reply_text("Format tidak valid. Gunakan /log agra atau /log agra @username.")
            return
    else:
        if context.args:
            await update.message.reply_text("Perintah /agra log hanya untuk riwayat pribadi. Gunakan /log agra untuk admin.")
            return
    
    if is_global:
        logs = await db.agra_report(conn, limit=20)
        title = "📜 <b>Global Agra Log (20 Terbaru)</b>"
    else:
        logs = await db.agra_report_user(conn, target_uid, limit=20)
        title = f"📜 <b>Log Agra {title_suffix} (20 Terbaru)</b>"
        
    if not logs:
        await update.message.reply_text(f"{title}\n\nBelum ada transaksi.")
        return
        
    lines = [title, ""]
    from bot.timefmt import format_local_time
    for r in logs:
        dt = format_local_time(r["created_at"])
        amt = r["amount"]
        sign = "+" if amt > 0 else ""
        t_name = r["target_first"] or r["target_username"] or "User"
        
        if is_global:
            lines.append(f"<code>{dt}</code> | {t_name} | <b>{sign}{amt}</b> | <i>{r['description']}</i>")
        else:
            lines.append(f"<b>{sign}{amt}</b> | <i>{r['description']}</i>")
                
    await update.message.reply_text("\n".join(lines)[:4000])




async def cmd_admin_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not can_approve_profile(row["role"], profile_from_row(row)):
        await update.message.reply_text("Hanya admin atau owner.")
        return
    msg = update.message
    parts = (msg.text or "").split()
    target_tid: int | None = None

    if len(parts) >= 2:
        token = parts[1].strip()
        if token.isdigit():
            if len(token) < 8:
                cur = await conn.execute("SELECT telegram_id FROM users ORDER BY created_at ASC, telegram_id ASC LIMIT 1 OFFSET ?", (int(token)-1,))
                rkr = await cur.fetchone()
                if not rkr:
                    await update.message.reply_text("User dengan No. ID tsb tidak ditemukan.")
                    return
                target_tid = rkr["telegram_id"]
            else:
                target_tid = int(token)
        else:
            ids = await db.find_ids_by_usernames(conn, [token])
            if not ids:
                await update.message.reply_text("User tidak ditemukan.")
                return
            target_tid = ids[0]
    elif msg.reply_to_message and msg.reply_to_message.from_user:
        target_tid = msg.reply_to_message.from_user.id

    if not target_tid:
        await update.message.reply_text(
            "Balas pesan user yang ingin diedit, atau:\n"
            "<code>/admin_data &lt;telegram_id/username/no_id&gt;</code>",
        )
        return
    trow = await user_row(conn, db, target_tid)
    if not trow:
        await update.message.reply_text("User belum pernah /start.")
        return
    context.user_data[ADMIN_TARGET_KEY] = target_tid
    _multi_clear(context)
    await db.set_onboarding_step(conn, actor, None)
    un = trow["username"] or "—"
    await update.message.reply_text(
        f"Edit profil <code>{target_tid}</code> (@{un}). "
        f"Pilih field — tersimpan langsung, tanpa persetujuan:",
        reply_markup=_admin_profile_keyboard(),
    )


def _daftar_clean_display(s: str) -> str:
    return (s or "—").replace("\n", " ").strip()[:120]


def _daftar_format_lines(
    entries: list[tuple[str, str | None, int]],
    *,
    show_telegram_id: bool = False,
) -> list[str]:
    lines = []
    for idx, (name, uname, tid) in enumerate(entries, 1):
        dn = html.escape(_daftar_clean_display(name))
        prefix = f"<code>{tid}</code> " if show_telegram_id else ""
        if uname:
            lines.append(f"{idx}. {prefix}{dn} — @{html.escape(uname)}")
        else:
            lines.append(f"{idx}. {prefix}{dn} — (tanpa username)")
    return lines


async def _reply_daftar_chunks(
    update: Update,
    title: str,
    lines: list[str],
    *,
    max_lines: int = 40,
    max_chars: int = 3400,
    pause_sec: float = 0.45,
) -> None:
    if not lines:
        await update.message.reply_text(f"{title}\n\nKosong.")
        return
    chunks: list[list[str]] = []
    buf: list[str] = []
    char_count = 0
    for line in lines:
        add_len = len(line) + 1
        if buf and (char_count + add_len > max_chars or len(buf) >= max_lines):
            chunks.append(buf)
            buf = []
            char_count = 0
        buf.append(line)
        char_count += add_len
    if buf:
        chunks.append(buf)
    total = len(chunks)
    for i, part in enumerate(chunks):
        head = title if total == 1 else f"{title} ({i + 1}/{total})"
        body = "\n".join(part)
        await update.message.reply_text(f"{head}\n\n{body}")
        if i < total - 1:
            await asyncio.sleep(pause_sec)


async def cmd_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    profile = profile_from_row(row) if row else {}
    dean_mode = can_daftar_as_dean(row["role"], profile) if row else False
    dean_fid = dean_faculty_id(profile) if dean_mode else ""
    lec_mode = can_daftar_as_lecturer(row["role"], profile) if row else False
    lec_cids = lecturer_class_ids(profile) if lec_mode else []

    if not row or not (can_report(row["role"], profile) or dean_mode or lec_mode):
        await update.message.reply_text(
            "Hanya admin, owner, dekan, atau dosen/coach (dengan lingkup yang sudah diisi)."
        )
        return
    if not context.args:
        await update.message.reply_text(
            "<b>Menu Daftar Pengguna:</b>\n"
            "<code>/daftar sisya</code> — Mahasiswa & BEM\n"
            "<code>/daftar charya</code> — Staf, Admin, Owner\n"
            "<code>/daftar pravesin</code> — MABA\n"
            "<code>/daftar publik</code> — Publik/Eksternal\n"
            "<code>/daftar fakultas &lt;id&gt;</code>\n"
            "<code>/daftar jurusan &lt;id&gt;</code>\n"
            "<code>/daftar kelas &lt;id&gt;</code>\n"
            "<code>/daftar ukm &lt;id&gt;</code>\n"
            "<code>/daftar all_staf</code>\n\n"
            "<b>Info Data Server (Admin/Owner):</b>\n"
            "<code>/daftar grup</code> — Lihat daftar grup yang diikuti bot\n"
            "<code>/daftar channel</code> — Lihat daftar channel yang diikuti bot\n\n"
            "Gunakan <code>/daftar id &lt;jenis&gt;</code> untuk memunculkan Telegram ID pengguna."
            + (
                "\n\n<i>Catatan: Dekan/Dosen hanya melihat hasil di lingkup masing-masing.</i>"
                if (dean_mode and dean_fid) or (lec_mode and lec_cids)
                else ""
            )
        )
        return
        
    if len(context.args) == 1:
        arg_lower = context.args[0].lower()
        if arg_lower == "id":
            return await cmd_list_id(update, context)
        elif arg_lower == "grup":
            return await cmd_list_grup(update, context)
        elif arg_lower == "channel":
            return await cmd_list_channel(update, context)

    show_telegram_id = False
    kind_idx = 0
    if len(context.args) >= 2 and context.args[0].lower() == "id":
        show_telegram_id = True
        kind_idx = 1
    kind = context.args[kind_idx].lower() if len(context.args) > kind_idx else ""
    # For sub-arguments like fakultas <id>, context.args will have them at kind_idx + 1
    parts_from_args = ["/daftar"] + context.args
    # Re-map parts logic:
    # Instead of rewriting all `len(parts) > kind_idx + 1` to `len(context.args) > kind_idx + 1`, 
    # we can just mock parts:
    parts = ["/daftar"] + context.args
    # Adjust kind_idx for parts array (since parts has the command at index 0)
    kind_idx += 1
    cur = await conn.execute(
        """
        SELECT telegram_id, username, first_name, last_name, role, profile_json
        FROM users
        ORDER BY created_at ASC, telegram_id ASC
        """
    )
    all_rows = await cur.fetchall()
    matching: list[tuple[str, str | None, int]] = []
    title = "Daftar"

    def push_row(r, p: dict) -> None:
        name = (
            p.get("full_name")
            or f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            or "—"
        )
        matching.append((name, r["username"], int(r["telegram_id"])))

    if kind == "all":
        title = "Daftar semua user"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            push_row(r, p)
    elif kind == "sisya":
        title = "Daftar Sisya"
        for r in all_rows:
            if r["role"] in (ROLE_STUDENT, ROLE_BEM):
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "charya":
        title = "Daftar Charya"
        for r in all_rows:
            if r["role"] in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "pravesin":
        title = "Daftar Pravesin"
        for r in all_rows:
            if r["role"] == ROLE_MABA:
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "publik":
        title = "Daftar Publik"
        for r in all_rows:
            if r["role"] == ROLE_PUBLIC:
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "dosen":
        title = "Daftar dosen"
        for r in all_rows:
            if r["role"] in (ROLE_INTERNAL, ROLE_ADMIN, ROLE_OWNER):
                p = json.loads(r["profile_json"] or "{}")
                p_jabs = normalize_multi_choice_value(p.get("position_detail"))
                if "d_dosen" in p_jabs or "d_guru_besar" in p_jabs:
                    push_row(r, p)
    elif kind == "fakultas" and len(parts) > kind_idx + 1:
        fid = parts[kind_idx + 1].lower()
        title = f"Daftar — fakultas {fid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            if p.get("faculty") == fid:
                push_row(r, p)
    elif kind == "jurusan" and len(parts) > kind_idx + 1:
        mid = parts[kind_idx + 1].lower()
        title = f"Daftar — jurusan {mid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            if p.get("major") == mid:
                push_row(r, p)
    elif kind == "kelas" and len(parts) > kind_idx + 1:
        cid = parts[kind_idx + 1].lower()
        title = f"Daftar — kelas {cid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            enrolled = normalize_multi_choice_value(p.get("class_enrolled"))
            teaching = normalize_multi_choice_value(p.get("teaching_classes"))
            if cid in enrolled or cid in teaching:
                push_row(r, p)
    elif kind == "ukm" and len(parts) > kind_idx + 1:
        uid = parts[kind_idx + 1].lower()
        title = f"Daftar — UKM {uid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            enrolled = normalize_multi_choice_value(p.get("club_enrolled"))
            if uid in enrolled:
                push_row(r, p)
    else:
        await update.message.reply_text(
            "Format tidak dikenali. Ketik /daftar untuk bantuan singkat."
        )
        return

    is_global_admin = row["role"] in (ROLE_OWNER, ROLE_ADMIN)
    if not is_global_admin and ((dean_mode and dean_fid) or (lec_mode and lec_cids)):
        kept: list[tuple[str, str | None, int]] = []
        for name, un, tid in matching:
            r = next((x for x in all_rows if int(x["telegram_id"]) == tid), None)
            if not r:
                continue
            p = json.loads(r["profile_json"] or "{}")
            
            in_scope = False
            if dean_mode and dean_fid and user_in_dean_faculty_scope(p, dean_fid):
                in_scope = True
            if not in_scope and lec_mode and lec_cids and user_in_lecturer_scope(p, lec_cids):
                in_scope = True
                
            if in_scope:
                kept.append((name, un, tid))
        matching = kept

    # Removed alphabetical sort to preserve the SQL order (created_at ASC)
    out_lines = _daftar_format_lines(matching, show_telegram_id=show_telegram_id)
    await db.add_audit(
        conn,
        update.effective_user.id,
        "daftar",
        f"{kind} id={int(show_telegram_id)} count={len(matching)}",
    )
    await _reply_daftar_chunks(
        update,
        title,
        out_lines,
    )


async def cmd_list_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    profile = profile_from_row(row) if row else {}
    dean_mode = can_daftar_as_dean(row["role"], profile) if row else False
    lec_mode = can_daftar_as_lecturer(row["role"], profile) if row else False

    if not row or not (can_report(row["role"], profile) or dean_mode or lec_mode):
        await update.message.reply_text(
            "Hanya admin, owner, dekan, atau dosen/coach yang bisa melihat daftar ID."
        )
        return

    lines = []
    
    lines.append("🏢 <b>FAKULTAS</b>")
    lines.append("<blockquote>")
    for f in CHOICES.get("faculties", []):
        lines.append(f"<code>{f.get('id', '')}</code> : {f.get('label', '')}")
    lines.append("\n</blockquote>")
    
    lines.append("📚 <b>JURUSAN</b>")
    lines.append("<blockquote>")
    for m in CHOICES.get("majors", []):
        lines.append(f"<code>{m.get('id', '')}</code> : {m.get('label', '')}")
    lines.append("\n</blockquote>")
    
    lines.append("🏫 <b>KELAS</b>")
    lines.append("<blockquote>")
    for c in CHOICES.get("classes", []):
        lines.append(f"<code>{c.get('id', '')}</code> : {c.get('label', '')}")
    lines.append("\n</blockquote>")

    lines.append("🏆 <b>UKM</b>")
    lines.append("<blockquote>")
    for u in CHOICES.get("clubs", []):
        lines.append(f"<code>{u.get('id', '')}</code> : {u.get('label', '')}")
    lines.append("\n</blockquote>")
        
    lines.append("⠀")
        
    await _reply_daftar_chunks(
        update,
        "Daftar ID Unit",
        lines
    )


async def cmd_list_grup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Hanya admin atau owner yang bisa menggunakan fitur ini.")
        return

    chats = await db.list_active_bot_chats(conn, chat_type="group")
    if not chats:
        await update.message.reply_text("Bot belum terdeteksi aktif di grup mana pun.")
        return

    lines = ["<b>Daftar Grup yang Diikuti Bot:</b>", ""]
    for cid, title in chats:
        lines.append(f"<code>{cid}</code> — {title}")
    
    await update.message.reply_text("\n".join(lines))


async def cmd_list_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Hanya admin atau owner yang bisa menggunakan fitur ini.")
        return

    chats = await db.list_active_bot_chats(conn, chat_type="channel")
    if not chats:
        await update.message.reply_text("Bot belum terdeteksi aktif di channel mana pun.")
        return

    lines = ["<b>Daftar Channel yang Diikuti Bot:</b>", ""]
    for cid, title in chats:
        lines.append(f"<code>{cid}</code> — {title}")
    
    await update.message.reply_text("\n".join(lines))


async def cmd_setrole(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Hanya owner yang bisa /setrole.")
        return
    msg = update.message
    parsed = parse_setrole_command(msg)
    if not parsed:
        await update.message.reply_text(
            "Pakai:\n"
            "<code>/setrole <admin|internal|student|maba|public> @user1 @user2</code>\n"
            "atau balas pesan seseorang lalu <code>/setrole <role></code>\n\n"
            "Owner tetap hanya satu (di .env); tidak bisa set owner ke orang lain.",
        )
        return
    role = parsed.role
    if role not in (
        ROLE_OWNER,
        ROLE_ADMIN,
        ROLE_INTERNAL,
        ROLE_BEM,
        ROLE_STUDENT,
        ROLE_MABA,
        ROLE_PUBLIC,
    ):
        await update.message.reply_text(
            "Role tidak dikenal. Gunakan admin, internal, bem, student, maba, atau public."
        )
        return
    conn = _conn(context)
    db = _db(context)
    extra = await db.find_ids_by_usernames(conn, parsed.mention_usernames)
    targets: set[int] = set(parsed.target_ids) | set(extra)
    if not targets:
        await update.message.reply_text("Sebutkan user dengan @mention atau reply pesannya.")
        return
    if role == ROLE_OWNER:
        if len(targets) > 1:
            await update.message.reply_text(
                "Hanya satu akun yang bisa jadi owner (OWNER_ID di .env)."
            )
            return
        tid_one = next(iter(targets))
        if tid_one != OWNER_ID:
            await update.message.reply_text(
                "Tidak bisa menjadikan user lain sebagai owner. Gunakan admin/lecturer/student."
            )
            return
    lines_out: list[str] = []
    actor = update.effective_user.id
    for tid in sorted(targets):
        urow = await user_row(conn, db, tid)
        if not urow:
            uname = "(tanpa username)"
            try:
                chat = await context.bot.get_chat(tid)
                if chat.username:
                    uname = f"@{chat.username}"
            except Exception:
                pass
            lines_out.append(f"• {uname} belum /start — dilewati.")
            continue
        prof = profile_from_row(urow)
        full_name = (
            prof.get("full_name")
            or f"{urow['first_name'] or ''} {urow['last_name'] or ''}".strip()
            or (f"@{urow['username']}" if urow["username"] else str(tid))
        )
        if role == ROLE_OWNER and tid != OWNER_ID:
            lines_out.append(f"• {full_name} — tidak bisa dijadikan owner.")
            continue
        await db.set_role(conn, tid, role)
        await db.add_audit(conn, actor, "set_role", f"{tid}->{role}")
        await _revalidate_filtered_choice_fields(conn, db, tid)
        lines_out.append(f"• {full_name} → {role_display(role)}")
        
        extra_text = ""
        if role == ROLE_MABA:
            mg = prof.get("maba_group")
            if not mg:
                cur_maba = await conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'maba'")
                maba_order_row = await cur_maba.fetchone()
                m_order = int(maba_order_row["c"]) if maba_order_row else 1
                mg = ((m_order - 1) % 4) + 1
                await db.set_profile_partial(conn, tid, {"maba_group": mg})
            
            from bot.settings import MABA_GROUP_GIDS, MABA_GROUP_NAMES, KELOMPOK_GID
            link = "(Grup kelompok belum disetel oleh admin)"
            try:
                if len(MABA_GROUP_GIDS) >= mg:
                    gid = MABA_GROUP_GIDS[mg - 1]
                    invite = await context.bot.create_chat_invite_link(
                        chat_id=gid, 
                        member_limit=1, 
                        name=f"Maba {tid}"
                    )
                    link = invite.invite_link
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Gagal membuat invite link Maba {tid}: {e}")
                link = "(Gagal mendapatkan tautan grup. Pastikan bot adalah admin di grup kelompok.)"
                
            extra_text = f"\n\nKamu ditempatkan di Kelompok {MABA_GROUP_NAMES.get(mg, mg)}.\nSilakan bergabung ke grup kelompokmu:\n{link}"

            if KELOMPOK_GID:
                try:
                    name_str = prof.get("full_name", "Tanpa Nama")
                    uname_str = f"@{urow['username']}" if urow.get("username") else "-"
                    msg_kelompok = (
                        f"📣 **Alokasi Kelompok MABA (Jalur Admin)**\n\n"
                        f"**Nama:** [{name_str}](tg://user?id={tid})\n"
                        f"**Username:** {uname_str}\n"
                        f"**Kelompok:** {MABA_GROUP_NAMES.get(mg, mg)}"
                    )
                    await context.bot.send_message(chat_id=KELOMPOK_GID, text=msg_kelompok, parse_mode="Markdown")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Gagal mengirim info kelompok admin ke {KELOMPOK_GID}: {e}")
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"Peran kamu diubah menjadi: <b>{role_display(role)}</b>{extra_text}",
            )
        except Exception:
            pass
    await update.message.reply_text(
        "Set role selesai:\n" + "\n".join(lines_out)[:4000]
    )

async def cmd_owner_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not is_owner(update.effective_user.id):
        await update.message.reply_text("Hanya owner yang berhak memicu menu reset ini.")
        return

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Semua (tanpa users)", callback_data="orreset:act:ALL"[:64])],
            [
                InlineKeyboardButton("🧾 Presensi: semua", callback_data="orreset:act:ATT_ALL"[:64]),
                InlineKeyboardButton("📚 Presensi: per matkul", callback_data="orreset:act:ATT_CLASS"[:64]),
            ],
            [InlineKeyboardButton("🆔 Presensi: per id", callback_data="orreset:act:ATT_SESSION"[:64])],
            [
                InlineKeyboardButton("💳 Agra: semua", callback_data="orreset:act:AGRA_ALL"[:64]),
                InlineKeyboardButton("👤 Agra: per user", callback_data="orreset:act:AGRA_USER"[:64]),
            ],
            [
                InlineKeyboardButton("🧩 Audit log: semua", callback_data="orreset:act:AUD_ALL"[:64]),
                InlineKeyboardButton("♻️ Reset semua data per user", callback_data="orreset:act:USER_ALL"[:64]),
            ],
            [
                InlineKeyboardButton(
                    "🧼 Reset semua user (kecuali env)",
                    callback_data="orreset:act:USER_ALL_EXCEPT_ENV"[:64],
                ),
                InlineKeyboardButton("🧾 Requests: semua", callback_data="orreset:act:REQ_ALL"[:64]),
            ],
            [
                InlineKeyboardButton("📝 Tugas: semua", callback_data="orreset:act:TASK_ALL"[:64]),
            ],
            [
                InlineKeyboardButton(
                    "🎓 RESET PERIODE AKADEMIK",
                    callback_data="orreset:act:ACADEMIC_PERIOD"[:64],
                )
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="orreset:cancel"[:64])],
        ]
    )

    await update.message.reply_text(
        "Menu reset data (owner). Pilih varian, lalu konfirmasi untuk menghapus data.",
        reply_markup=kb,
    )


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not can_approve_profile(row["role"], profile_from_row(row)):
        await update.message.reply_text("Hanya admin/owner.")
        return
    pending = await db.list_pending_profile_requests(conn)
    if not pending:
        await update.message.reply_text("Tidak ada pengajuan tertunda.")
        return
    for p in pending[:10]:
        prop = json.loads(p["proposed_json"])
        preview = json.dumps(prop, ensure_ascii=False)[:180]
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅", callback_data=f"a:{p['id']}:1"[:32]
                    ),
                    InlineKeyboardButton(
                        "❌", callback_data=f"a:{p['id']}:0"[:32]
                    ),
                ]
            ]
        )
        await update.message.reply_text(
            f"#{p['id']} dari <code>{p['telegram_id']}</code>\n<code>{preview}</code>",
            reply_markup=kb,
        )


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not can_view_sensitive_logs(row["role"], profile_from_row(row)):
        await update.message.reply_text("Anda tidak berhak melihat log audit.")
        return
    if not context.args or context.args[0].lower() == "help":
        await update.message.reply_text(
            "<b>Menu Log Sistem:</b>\n"
            "<code>/log terbaru</code> — Ringkasan 15 log terbaru\n"
            "<code>/log agra [all|@user]</code> — Riwayat Agra\n"
            "<code>/log fakultas &lt;id&gt;</code> — Filter fakultas\n"
            "<code>/log jurusan &lt;id_jurusan&gt;</code> — Filter jurusan\n"
            "<code>/log kelas &lt;id_kelas&gt;</code> — Filter kelas\n"
            "<code>/log ukm &lt;id_ukm&gt;</code> — Filter UKM\n"
            "<code>/log nama &lt;potongan nama&gt;</code> — Filter nama\n"
        )
        return

    faculty_id = major_id = class_id = ukm_id = name_sub = None
    if len(context.args) >= 2 and context.args[0].lower() == "fakultas":
        faculty_id = context.args[1]
    elif len(context.args) >= 2 and context.args[0].lower() == "jurusan":
        major_id = context.args[1]
    elif len(context.args) >= 2 and context.args[0].lower() == "kelas":
        class_id = context.args[1]
    elif len(context.args) >= 2 and context.args[0].lower() == "ukm":
        ukm_id = context.args[1]
    elif len(context.args) >= 2 and context.args[0].lower() == "nama":
        name_sub = " ".join(context.args[1:])
    elif len(context.args) >= 1 and context.args[0].lower() == "agra":
        context.args = context.args[1:]
        context.is_from_log_cmd = True
        return await cmd_agralog(update, context)
    elif len(context.args) == 1 and context.args[0].lower() == "terbaru":
        pass
    else:
        await update.message.reply_text("Filter log tidak valid. Ketik /log untuk panduan.")
        return

    filtered = faculty_id is not None or major_id is not None or class_id is not None or ukm_id is not None or name_sub is not None
    if filtered:
        ids = await db.user_ids_matching_profile_filter(
            conn,
            faculty_id=faculty_id,
            major_id=major_id,
            class_id=class_id,
            ukm_id=ukm_id,
            name_substring=name_sub,
        )
        if not ids:
            await update.message.reply_text("Tidak ada user yang cocok dengan filter.")
            return
        audit_rows = await db.audit_log_for_actors(conn, ids, limit=20)
        agra_rows = await db.agra_ledger_for_targets(conn, ids, limit=15)
        hdr = []
        if faculty_id:
            hdr.append(f"fakultas <code>{faculty_id}</code>")
        if major_id:
            hdr.append(f"jurusan <code>{major_id}</code>")
        if class_id:
            hdr.append(f"kelas <code>{class_id}</code>")
        if ukm_id:
            hdr.append(f"ukm <code>{ukm_id}</code>")
        if name_sub:
            hdr.append(f"nama <code>{name_sub}</code>")
        lines = [f"<b>Log</b> (filter: {', '.join(hdr)})", ""]
    else:
        cur = await conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 15",
        )
        audit_rows = await cur.fetchall()
        agra_rows = await db.agra_report(conn, limit=8)
        lines = ["<b>Log audit (15 terakhir)</b>", ""]

    lines.append("<b>Audit</b>")
    if not audit_rows:
        lines.append("<i>Kosong.</i>")
    else:
        for r in audit_rows:
            ts = format_local_time(r["created_at"])
            det = (r["detail"] or "")[:120]
            lines.append(f"• <code>{ts}</code> <code>{r['action']}</code> — {det}")
    lines.extend(["", "<b>Agra (deskripsi — mod only)</b>"])
    if not agra_rows:
        lines.append("<i>Kosong.</i>")
    else:
        for g in agra_rows:
            ts = format_local_time(g["created_at"])
            lines.append(
                f"• <code>{ts}</code> →<code>{g['target_telegram_id']}</code> <b>{g['amount']}</b> — <i>{g['description'][:80]}</i>"
            )
    await update.message.reply_text(
        "\n".join(lines)[:4000]
    )


async def cmd_all_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    await update.message.reply_text(
        "<b>Menu Mention Grup (/tagall)</b>\n"
        "<code>/all [pesan]</code> — Mention semua anggota grup\n"
        "<code>/all &lt;role&gt; [pesan]</code> — Filter role (contoh: sisya, pravesin, charya, publik)\n"
        "<code>/all fakultas &lt;id&gt; [pesan]</code> — Filter fakultas\n"
        "<code>/all jurusan &lt;id&gt; [pesan]</code> — Filter jurusan\n"
        "<code>/all kelas &lt;id&gt; [pesan]</code> — Filter kelas\n"
        "<code>/all ukm &lt;id&gt; [pesan]</code> — Filter UKM\n\n"
        "Pesan bersifat opsional. Data yang dikirim akan otomatis dipecah agar tidak terkena limit."
    )

async def cmd_tagall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
        
    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not can_tag_all(row["role"], profile_from_row(row)):
        await update.message.reply_text("Hanya Staf, Pengajar, atau BEM yang bisa mengakses menu ini.")
        return
        
    return await cmd_all_help(update, context)

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("/all hanya bisa dipakai di grup.")
        return

    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not can_tag_all(row["role"], profile_from_row(row)):
        await update.message.reply_text("Hanya Staf, Pengajar, atau BEM yang bisa melakukan tag all.")
        return

    # Request userbot to fetch members
    chat_id_str = str(update.effective_chat.id)
    req_id = await db.create_userbot_request(conn, chat_id_str, "GET_MEMBERS")
    
    # Send waiting message
    wait_msg = await update.message.reply_text("⏳ Mohon menunggu...")
    
    # Poll for result up to 10 seconds
    import asyncio, json
    userbot_ids = []
    success = False
    for _ in range(10):
        await asyncio.sleep(1)
        req_row = await db.get_userbot_request(conn, req_id)
        if req_row and req_row["status"] == "DONE":
            try:
                userbot_ids = json.loads(req_row["result"])
                success = True
            except Exception:
                pass
            break
        elif req_row and req_row["status"] == "ERROR":
            break
            
    # Fallback to group_seen_users if userbot fails
    if success and userbot_ids:
        all_ids = userbot_ids
    else:
        all_ids = await db.list_group_seen_user_ids(conn, update.effective_chat.id)
        
    try:
        await wait_msg.delete()
    except:
        pass
    ids = [tid for tid in all_ids if tid != actor]
    if not ids:
        await update.message.reply_text(
            "Belum ada user yang terdeteksi bot di grup ini."
        )
        return

    raw_text = (update.message.text or update.message.caption or "").strip()
    parts = raw_text.split(maxsplit=3)
    
    filter_type = None
    filter_val = None
    custom_body = ""
    
    if len(parts) > 1:
        possible_type = parts[1].lower()
        if possible_type in ("role", "fakultas", "jurusan", "ukm", "kelas"):
            if len(parts) > 2:
                filter_type = possible_type
                filter_val = parts[2].lower()
                if len(parts) > 3:
                    custom_body = parts[3]
            else:
                await update.message.reply_text(f"Nilai {possible_type} belum ditentukan.")
                return
        elif possible_type in ("umum", "publik", "pravesin", "sisya", "charya"):
            filter_type = possible_type
            if len(parts) > 2:
                custom_body = raw_text.split(maxsplit=2)[2]
        else:
            # Not a filter keyword, so it's a message for all
            custom_body = raw_text.split(maxsplit=1)[1]
    
    filtered_ids = []
    if filter_type:
        for tid in ids:
            u_row = await user_row(conn, db, tid)
            if not u_row:
                continue
            u_role = u_row["role"]
            u_prof = profile_from_row(u_row)
            
            match = False
            if filter_type == "role" and u_role == filter_val:
                match = True
            elif filter_type == "publik" and u_role == "public":
                match = True
            elif filter_type == "pravesin" and u_role == "maba":
                match = True
            elif filter_type == "sisya" and u_role in ("student", "bem"):
                match = True
            elif filter_type == "charya" and u_role in ("internal", "admin", "owner"):
                match = True
            elif filter_type == "fakultas" and str(u_prof.get("faculty", "")).lower() == filter_val:
                match = True
            elif filter_type == "jurusan" and str(u_prof.get("major", "")).lower() == filter_val:
                match = True
            elif filter_type == "umum":
                enrolled = normalize_multi_choice_value(u_prof.get("class_enrolled", []))
                teaching = normalize_multi_choice_value(u_prof.get("teaching_classes", []))
                if any(str(x).lower().startswith("umum_") for x in enrolled + teaching):
                    match = True
            elif filter_type == "ukm":
                enrolled = normalize_multi_choice_value(u_prof.get("club_enrolled", []))
                if filter_val in [str(x).lower() for x in enrolled]:
                    match = True
            elif filter_type == "kelas":
                enrolled = normalize_multi_choice_value(u_prof.get("class_enrolled", []))
                teaching = normalize_multi_choice_value(u_prof.get("teaching_classes", []))
                if filter_val in [str(x).lower() for x in enrolled + teaching]:
                    match = True
            
            if match:
                filtered_ids.append(tid)
        ids = filtered_ids

    if not ids:
        await update.message.reply_text("Tidak ada user yang cocok dengan filter tagall tersebut.")
        return

    await _execute_mention_batch(update, context, ids, custom_body)

async def _execute_mention_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, ids: list[int], custom_body: str) -> None:
    import html
    custom_body_html = html.escape(custom_body)

    batch_size = 7
    pause_sec = 0.8
    chunks = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]
    total = len(chunks)

    # Emoji love berbagai warna
    hearts = ["❤", "🧡", "💛", "💚", "💙", "💜", "🤎", "🖤", "🤍", "💖", "💗", "💘", "💝", "💕"]

    for idx, chunk in enumerate(chunks, start=1):
        mentions = " ".join(
            f'<a href="tg://user?id={tid}">{random.choice(hearts)}</a>' for tid in chunk
        )
        header = (
            f"Tag semua ({idx}/{total})" if total > 1 else "Tag semua"
        )
        text = (
            f"{custom_body_html}\n\n{mentions}"
            if custom_body_html
            else f"{header}\n\n{mentions}"
        )
        reply_to_id = update.message.reply_to_message.message_id if update.message.reply_to_message else None
        await update.message.reply_text(
            text,
            disable_web_page_preview=True,
            reply_to_message_id=reply_to_id
        )
        if idx < total:
            await asyncio.sleep(pause_sec)

    if custom_body_html:
        await update.message.reply_text("Summon ended.")

    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    await db.add_audit(
        conn,
        actor,
        "tagall",
        f"chat={update.effective_chat.id} count={len(ids)} batches={total} msg={int(bool(custom_body))}",
    )


async def cmd_agratop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    
    where_clause = ""
    title_suffix = ""
    
    if context.args:
        sub = context.args[0].lower()
        if sub == "sisya":
            where_clause = "WHERE u.role IN ('student', 'bem')"
            title_suffix = " (Sisya)"
        elif sub == "charya":
            where_clause = "WHERE u.role IN ('internal', 'admin', 'owner')"
            title_suffix = " (Charya)"
        elif sub == "publik":
            where_clause = "WHERE u.role = 'public'"
            title_suffix = " (Publik)"
        elif sub == "pravesin":
            where_clause = "WHERE u.role = 'maba'"
            title_suffix = " (Pravesin)"
    cur = await conn.execute(
        f"""
        SELECT t.target_telegram_id, t.total, u.profile_json, u.first_name, u.username
        FROM (
            SELECT target_telegram_id, SUM(amount) AS total
            FROM agra_ledger
            GROUP BY target_telegram_id
        ) t
        JOIN users u ON u.telegram_id = t.target_telegram_id
        {where_clause}
        ORDER BY t.total DESC
        LIMIT 17
        """
    )
    rows = await cur.fetchall()
    lines = [f"Top 17 Agra{title_suffix}"]
    if not rows:
        lines.append("Belum ada data.")
    else:
        for idx, r in enumerate(rows, start=1):
            pj = json.loads(r["profile_json"] or "{}")
            name = (
                pj.get("full_name")
                or r["first_name"]
                or (f"@{r['username']}" if r["username"] else None)
                or "—"
            )
            total_s = f"{r['total']:,}"
            lines.append(f"{idx}. {total_s} - {name}")
    await update.message.reply_text("\n".join(lines))


async def cmd_agra_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    role = row["role"] if row else ROLE_STUDENT
    prof = profile_from_row(row) if row else {}
    
    if not context.args:
        lines = [
            "<b>Menu Agra</b>",
            "<code>/agra top</code> — Lihat peringkat Agra (17 besar)",
            "<code>/agra top sisya</code> — Top 17 (Student & BEM)",
            "<code>/agra top charya</code> — Top 17 (Staf/Petinggi)",
            "<code>/agra top pravesin</code> — Top 17 (MABA)",
            "<code>/agra top publik</code> — Top 17 (Eksternal)",
            "<code>/agra log</code> — Lihat riwayat Agra pribadi"
        ]
        
        if can_manage_agra(role, prof):
            lines.extend([
                "",
                "<b>Admin Agra</b>",
                "<code>/add [nominal] @user | [deskripsi]</code>",
                "<code>/transfer [nominal] @user | [deskripsi]</code>"
            ])
        await update.message.reply_text("\n".join(lines))
        return
        
    subcmd = context.args[0].lower()
    original_args = context.args[:]
    context.args = context.args[1:]
    try:
        if subcmd == "top": await cmd_agratop(update, context)
        elif subcmd == "log": await cmd_agralog(update, context)
        else: await update.message.reply_text("Sub-command Agra tidak ditemukan. Gunakan /agra untuk melihat menu.")
    finally:
        context.args = original_args

async def cmd_pindah_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] != ROLE_OWNER:
        await update.message.reply_text("Hanya owner yang bisa memindahkan data.")
        return
        
    if len(context.args) < 2:
        await update.message.reply_text("Format: <code>/pindah_data &lt;id_lama|@username_lama&gt; &lt;id_baru|@username_baru&gt;</code>")
        return
        
    old_query = context.args[0]
    new_query = context.args[1]
    
    old_user = await db.get_user_by_username_or_id(conn, old_query)
    if not old_user:
        await update.message.reply_text(f"User lama {old_query} tidak ditemukan di database.")
        return
        
    new_user = await db.get_user_by_username_or_id(conn, new_query)
    new_id = int(new_user["telegram_id"]) if new_user else (int(new_query) if new_query.isdigit() else None)
    
    if not new_id:
        await update.message.reply_text(f"User baru {new_query} tidak ditemukan. Jika belum pernah /start, harus pakai ID berupa angka.")
        return
        
    old_id = int(old_user["telegram_id"])
    if old_id == new_id:
        await update.message.reply_text("ID lama dan baru sama!")
        return
        
    success = await db.migrate_user_data(conn, old_id, new_id)
    if success:
        await update.message.reply_text(f"Berhasil memindahkan data dari <code>{old_query}</code> ke <code>{new_query}</code>.")
    else:
        await update.message.reply_text("Gagal memindahkan data.")

async def cmd_cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
        await update.message.reply_text("Hanya staf/admin yang bisa cek user.")
        return
        
    if not context.args:
        await update.message.reply_text("Format: <code>/cek_user &lt;ID|@username&gt;</code>")
        return
        
    query = context.args[0]
    u = await db.get_user_by_username_or_id(conn, query)
    if not u:
        await update.message.reply_text(f"User {query} tidak ditemukan.")
        return
        
    pj = json.loads(u["profile_json"] or "{}")
    name = pj.get("full_name") or u["first_name"] or "—"
    
    lines = [
        f"<b>Data User:</b>",
        f"ID: <code>{u['telegram_id']}</code>",
        f"Username: @{u['username']}" if u['username'] else "Username: —",
        f"Nama: {name}",
        f"Role: {u['role']}"
    ]
    await update.message.reply_text("\n".join(lines))

async def cmd_orreset_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not is_owner(update.effective_user.id):
        await update.message.reply_text("Hanya owner yang bisa melakukan reset user.")
        return
        
    if not context.args:
        await update.message.reply_text("Format: <code>/orreset_user &lt;ID|@username&gt;</code>")
        return
        
    query = context.args[0]
    u = await db.get_user_by_username_or_id(conn, query)
    if not u:
        await update.message.reply_text(f"User {query} tidak ditemukan.")
        return
        
    uid = int(u["telegram_id"])
    result = await db.reset_user_all_data(conn, uid)
    if isinstance(result, dict):
        lines = [f"• {k}: <code>{v}</code>" for k, v in result.items()]
        await update.message.reply_text("<b>Reset semua data user selesai.</b>\n" + "\n".join(lines))
    else:
        await update.message.reply_text(f"<b>Reset selesai.</b>\n• count: <code>{result}</code>")

async def cmd_orreset_agra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not is_owner(update.effective_user.id):
        await update.message.reply_text("Hanya owner yang bisa melakukan reset agra.")
        return
        
    if not context.args:
        await update.message.reply_text("Format: <code>/orreset_agra &lt;ID|@username&gt;</code>")
        return
        
    query = context.args[0]
    u = await db.get_user_by_username_or_id(conn, query)
    if not u:
        await update.message.reply_text(f"User {query} tidak ditemukan.")
        return
        
    uid = int(u["telegram_id"])
    result = await db.reset_agra_for_user(conn, uid)
    if isinstance(result, dict):
        lines = [f"• {k}: <code>{v}</code>" for k, v in result.items()]
        await update.message.reply_text("<b>Reset agra user selesai.</b>\n" + "\n".join(lines))
    else:
        await update.message.reply_text(f"<b>Reset selesai.</b>\n• count: <code>{result}</code>")

async def cmd_addtag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("/addtag hanya bisa dipakai di grup.")
        return

    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not can_tag_all(row["role"], profile_from_row(row)):
        await update.message.reply_text("Hanya Staf, Pengajar, atau BEM yang bisa melakukan add tag.")
        return

    if not context.args:
        await update.message.reply_text("Format: <code>/addtag 123456, 789012, ...</code>")
        return

    raw_args = " ".join(context.args)
    parts = [p.strip() for p in raw_args.replace(",", " ").split() if p.strip().isdigit()]
    
    if not parts:
        await update.message.reply_text("Tidak ada Telegram ID valid yang ditemukan.")
        return

    added = 0
    chat_id = update.effective_chat.id
    for tid_str in parts:
        tid = int(tid_str)
        u_row = await user_row(conn, db, tid)
        if u_row:
            username = u_row["username"]
            first_name = u_row["first_name"]
            last_name = u_row["last_name"]
            is_bot = u_row["is_bot"]
        else:
            username = None
            first_name = f"Manual Added {tid}"
            last_name = None
            is_bot = 0

        await db.touch_group_seen_user(
            conn,
            chat_id=chat_id,
            telegram_id=tid,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_bot=bool(is_bot)
        )
        added += 1

    await update.message.reply_text(f"Berhasil menambahkan {added} ID ke daftar tagall grup ini.")

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] not in ("owner", "admin"):
        await update.message.reply_text("Hanya Owner atau Admin yang dapat mengelola data pengguna.")
        return

    if not context.args:
        lines = [
            "<b>Menu Manajemen Pengguna</b>",
            "<code>/users stats</code> — Menampilkan statistik total pengguna per role",
            "<code>/users find &lt;nama&gt;</code> — Mencari Telegram ID berdasarkan nama pengguna",
            "<code>/users staff</code> — Menampilkan daftar semua staf internal",
            "<code>/users admin</code> — Menampilkan daftar semua Admin dan Owner"
        ]
        await update.message.reply_text("\n".join(lines))
        return

    subcmd = context.args[0].lower()

    if subcmd == "stats":
        cur = await conn.execute("SELECT role, COUNT(*) as c FROM users GROUP BY role")
        rows = await cur.fetchall()
        
        total = 0
        role_counts = {}
        for r in rows:
            role = r["role"]
            c = r["c"]
            role_counts[role] = c
            total += c

        lines = [
            "<b>Statistik Pengguna</b>",
            f"Total Pengguna: <b>{total}</b>\n",
            "<b>Rincian per Role:</b>"
        ]
        
        for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"• {role.title()}: {count}")

        await update.message.reply_text("\n".join(lines))

    elif subcmd == "find":
        if len(context.args) < 2:
            await update.message.reply_text("Format: <code>/users find &lt;nama&gt;</code>")
            return
            
        query = " ".join(context.args[1:]).lower()
        matched = await db.user_ids_matching_profile_filter(conn, name_substring=query)
        
        # also search by first_name directly
        cur = await conn.execute("SELECT telegram_id FROM users WHERE lower(first_name) LIKE ?", (f"%{query}%",))
        first_name_matches = await cur.fetchall()
        for m in first_name_matches:
            if m["telegram_id"] not in matched:
                matched.append(m["telegram_id"])
        
        if not matched:
            await update.message.reply_text(f"Tidak ditemukan pengguna dengan nama mengandung '{query}'.")
            return
            
        lines = [f"<b>Hasil Pencarian '{query}' ({len(matched)} user):</b>"]
        for tid in matched[:50]: # limit to 50
            u_row = await user_row(conn, db, tid)
            if u_row:
                pj = profile_from_row(u_row)
                full_name = pj.get("full_name") or u_row["first_name"] or "Unknown"
                role = u_row["role"]
                lines.append(f"• <code>{tid}</code> - {full_name} ({role})")
                
        if len(matched) > 50:
            lines.append(f"<i>...dan {len(matched)-50} lainnya.</i>")
            
        await update.message.reply_text("\n".join(lines))

    elif subcmd == "staff":
        staff_ids = await db.get_all_staff_ids(conn)
        if not staff_ids:
            await update.message.reply_text("Belum ada staf internal terdaftar.")
            return
            
        lines = [f"<b>Daftar Staf Internal ({len(staff_ids)}):</b>"]
        for tid in staff_ids:
            u_row = await user_row(conn, db, tid)
            if u_row:
                username = f"@{u_row['username']}" if u_row["username"] else u_row["first_name"]
                lines.append(f"• <code>{tid}</code> - {username}")
        await update.message.reply_text("\n".join(lines))

    elif subcmd == "admin":
        admin_ids = await db.list_moderator_telegram_ids(conn)
        if not admin_ids:
            await update.message.reply_text("Tidak ada admin yang terdaftar.")
            return
            
        lines = [f"<b>Daftar Admin & Owner ({len(admin_ids)}):</b>"]
        for tid in admin_ids:
            u_row = await user_row(conn, db, tid)
            if u_row:
                username = f"@{u_row['username']}" if u_row["username"] else u_row["first_name"]
                role = u_row["role"]
                lines.append(f"• <code>{tid}</code> - {username} ({role})")
        await update.message.reply_text("\n".join(lines))
        
    else:
        await update.message.reply_text("Sub-perintah tidak dikenali. Ketik /users untuk melihat menu.")

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    
    uid = update.effective_user.id
    conn = _conn(context)
    db = context.application.bot_data["db"]
    
    u_row = await user_row(conn, db, uid)
    if not u_row:
        return
        
    role = u_row["role"]
    prof = profile_from_row(u_row)
    pos = prof.get("position_detail")
    
    from bot.settings import is_admin_elevated
    if not (is_admin_elevated(uid) or pos == "d_sekre"):
        await update.message.reply_text("⛔ Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return
        
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    
    target_id = None
    target_username_or_id = None
    
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        target_username_or_id = str(target_id)
    elif len(parts) > 1:
        target_username_or_id = parts[1].strip()
        t_row = await db.get_user_by_username_or_id(conn, target_username_or_id)
        if t_row:
            target_id = t_row["telegram_id"]
        elif target_username_or_id.isdigit():
            target_id = int(target_username_or_id)
    
    if not target_id:
        await update.message.reply_text("❌ Target tidak ditemukan. Gunakan: /kick @username, ID Telegram, atau reply pesannya.")
        return
        
    t_row = await user_row(conn, db, target_id)
    if not t_row:
        t_name = f"User {target_id}"
        t_role = "unknown"
    else:
        t_name = t_row["first_name"]
        t_role = t_row["role"]
    
    if is_admin_elevated(target_id) or t_role == ROLE_OWNER:
        await update.message.reply_text("⛔ Tidak bisa men-kick Owner/Admin.")
        return

    is_group = update.effective_chat.type in ("group", "supergroup")
    
    if is_group:
        chat_id = update.effective_chat.id
        await _do_kick(update, context, chat_id, target_id, t_name, is_group)
    else:
        groups = await db.list_active_bot_chats(conn)
        if not groups:
            await update.message.reply_text("⚠️ Bot belum dimasukkan ke grup manapun.")
            return
            
        if len(groups) == 1:
            chat_id = groups[0][0]
            await _do_kick(update, context, chat_id, target_id, t_name, is_group)
        else:
            keyboard = []
            for c_id, c_title in groups:
                keyboard.append([InlineKeyboardButton(c_title, callback_data=f"kick:{c_id}:{target_id}")])
            keyboard.append([InlineKeyboardButton("Batal", callback_data="kick:cancel:0")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Pilih grup tempat kamu ingin mengeluarkan <b>{html.escape(t_name)}</b>:",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

async def _do_kick(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, target_id: int, target_name: str, is_group: bool) -> None:
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        
        caller_name = update.effective_user.first_name
        
        if is_group:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚨 <b>{html.escape(target_name)}</b> telah dikeluarkan dari grup oleh <b>{html.escape(caller_name)}</b>.",
                parse_mode="HTML"
            )
        else:
            await update.effective_message.reply_text(f"✅ Berhasil mengeluarkan <b>{html.escape(target_name)}</b> dari grup.", parse_mode="HTML")
            from bot.settings import OWNER_ID
            if OWNER_ID and OWNER_ID != update.effective_user.id:
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"ℹ️ <b>{html.escape(caller_name)}</b> telah mengeluarkan <b>{html.escape(target_name)}</b> dari grup melalui PM.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Gagal mengeluarkan target. Bot mungkin bukan admin di grup tersebut.\n\nError: {e}")

async def on_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
        
    data = query.data
    parts = data.split(":")
    if len(parts) != 3:
        return
        
    action, chat_id_str, target_id_str = parts[0], parts[1], parts[2]
    
    if action != "kick":
        return
        
    await query.answer()
    
    if chat_id_str == "cancel":
        await query.edit_message_text("❌ Dibatalkan.")
        return
        
    try:
        chat_id = int(chat_id_str)
        target_id = int(target_id_str)
    except ValueError:
        return
        
    conn = _conn(context)
    db = context.application.bot_data["db"]
    t_row = await user_row(conn, db, target_id)
    t_name = t_row["first_name"] if t_row else "User"
    
    await query.edit_message_text("Memproses...")
    await _do_kick(update, context, chat_id, target_id, t_name, is_group=False)



async def cmd_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    profile = profile_from_row(row) if row else {}
    dean_mode = can_daftar_as_dean(row["role"], profile) if row else False
    dean_fid = dean_faculty_id(profile) if dean_mode else ""
    lec_mode = can_daftar_as_lecturer(row["role"], profile) if row else False
    lec_cids = lecturer_class_ids(profile) if lec_mode else []

    if not row or not (can_report(row["role"], profile) or dean_mode or lec_mode):
        await update.message.reply_text("Hanya admin, owner, dekan, atau dosen/coach.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan format seperti /daftar, contoh: /detail all, /detail mhs")
        return

    kind = context.args[0].lower()
    cur = await conn.execute(
        "SELECT telegram_id, username, first_name, last_name, role, profile_json FROM users"
    )
    all_rows = await cur.fetchall()
    
    parsed_users = []
    
    def push_row(r, p: dict) -> None:
        name = (p.get("full_name") or f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "—")
        bdate = p.get("birth_date") or ""
        muse = p.get("muse") or "—"
        dist = days_until_next_birthday(bdate)
        parsed_users.append({
            "tid": r["telegram_id"],
            "name": name,
            "username": r["username"],
            "bdate": bdate,
            "muse": muse,
            "dist": dist
        })

    title = "Detail Pengguna"
    if kind == "admin":
        for r in all_rows:
            if r["role"] in (ROLE_OWNER, ROLE_ADMIN):
                push_row(r, json.loads(r["profile_json"] or "{}"))
    elif kind == "all":
        for r in all_rows:
            push_row(r, json.loads(r["profile_json"] or "{}"))
    elif kind == "mhs":
        for r in all_rows:
            if r["role"] == ROLE_STUDENT:
                push_row(r, json.loads(r["profile_json"] or "{}"))
    elif kind == "staf":
        for r in all_rows:
            if r["role"] == ROLE_INTERNAL:
                p = json.loads(r["profile_json"] or "{}")
                p_jabs = normalize_multi_choice_value(p.get("position_detail"))
                if "d_dosen" not in p_jabs and "d_guru_besar" not in p_jabs:
                    push_row(r, p)
    elif kind == "all_staf":
        for r in all_rows:
            if r["role"] in (ROLE_ADMIN, ROLE_INTERNAL):
                push_row(r, json.loads(r["profile_json"] or "{}"))
    elif kind == "dosen":
        for r in all_rows:
            if r["role"] in (ROLE_INTERNAL, ROLE_ADMIN, ROLE_OWNER):
                p = json.loads(r["profile_json"] or "{}")
                p_jabs = normalize_multi_choice_value(p.get("position_detail"))
                if "d_dosen" in p_jabs or "d_guru_besar" in p_jabs:
                    push_row(r, p)
    else:
        await update.message.reply_text("Format tidak dikenali. Ketik /detail all atau mhs.")
        return

    is_global_admin = row["role"] in (ROLE_OWNER, ROLE_ADMIN)
    if not is_global_admin and ((dean_mode and dean_fid) or (lec_mode and lec_cids)):
        kept = []
        for u in parsed_users:
            r = next((x for x in all_rows if x["telegram_id"] == u["tid"]), None)
            if not r:
                continue
            p = json.loads(r["profile_json"] or "{}")
            
            in_scope = False
            if dean_mode and dean_fid and user_in_dean_faculty_scope(p, dean_fid):
                in_scope = True
            if not in_scope and lec_mode and lec_cids and user_in_lecturer_scope(p, lec_cids):
                in_scope = True
                
            if in_scope:
                kept.append(u)
        parsed_users = kept
        
    # Sort by closest birthday
    parsed_users.sort(key=lambda x: x["dist"])
    
    out_lines = []
    idx = 1
    for u in parsed_users:
        un = u['username']
        un_str = f" — @{html.escape(un)}" if un else " — (tanpa username)"
        bdate_str = html.escape(u['bdate']) if u['bdate'] else "—"
        out_lines.append(f"{idx}. {html.escape(u['name'])}{un_str}\n   {bdate_str} - {html.escape(u['muse'])}")
        idx += 1

    await db.add_audit(conn, update.effective_user.id, "detail", f"{kind} count={len(parsed_users)}")
    await _reply_daftar_chunks(update, title, out_lines)


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or row["role"] not in (ROLE_OWNER, ROLE_ADMIN):
        await update.message.reply_text("Tidak diizinkan.")
        return

    import os, json
    msg = await update.message.reply_text("Memulai ulang bot...")
    try:
        with open(".restart.json", "w") as f:
            json.dump({"chat_id": msg.chat_id, "message_id": msg.message_id}, f)
    except Exception:
        pass
    os.system("sudo systemctl restart botdhru")
