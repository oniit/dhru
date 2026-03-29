from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.agra_parse import parse_add_command
from bot.setrole_parse import parse_setrole_command
from bot.database import (
    ROLE_ADMIN,
    ROLE_LECTURER,
    ROLE_OWNER,
    ROLE_STAFF,
    ROLE_STUDENT,
    role_can_add_agra,
    role_can_approve_profile,
    role_can_open_presensi,
    role_can_report,
    role_can_view_sensitive_logs,
)
from bot.settings import (
    CHOICES,
    OWNER_ID,
    PROFILE_FIELDS,
    field_applies_to_role,
    filtered_choice_items,
    is_choice_allowed_for_profile,
    is_owner,
)
from bot.timefmt import format_local_time

from .common import (
    field_label_for_key,
    fields_for_role,
    format_profile_card,
    keyboard_for_choices,
    keyboard_for_multi_choices,
    missing_required_fields,
    moderator_chat_ids,
    profile_from_row,
    normalize_multi_choice_value,
    role_display,
    sync_roles_from_env,
    user_row,
)

MULTI_UD_KEY = "multi_select"
ADMIN_TARGET_KEY = "admin_profile_target"
LENGKAPI_DONE_KEY = "__lengkapi_done"


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
        if f.type != "choice" or not f.filter_by_field:
            continue
        if not field_applies_to_role(f, role):
            continue
        val = prof.get(f.key)
        if val is None or val == "":
            continue
        if not is_choice_allowed_for_profile(f, prof, str(val)):
            to_remove.append(f.key)
    if to_remove:
        await db.remove_profile_keys(conn, telegram_id, to_remove)


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
    await _revalidate_filtered_choice_fields(conn, db, u.id)
    row = await user_row(conn, db, u.id)
    profile = profile_from_row(row)
    miss = missing_required_fields(profile, row["role"])

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


def help_for_role(role: str) -> str:
    lines = [
        "*Perintah umum*",
        "/start — Daftar & sinkron profil Telegram",
        "/profile — Profil & total Agra",
        "/lengkapi — Isi data wajib awal (sekali)",
        "_Mahasiswa: isi Fakultas sebelum Jurusan._",
        "/ubah — Ajukan perubahan (disetujui admin)",
        "/hadir — Presensi ke sesi yang dibuka",
        "",
        "*Untuk semua pengguna*",
        "/top\\_agra — Peringkat Agra (17 besar)",
        "",
    ]
    if role_can_add_agra(role):
        lines.extend(
            [
                "*Agra (dosen/admin/owner)*",
                "/add <nominal> @user … \\| <deskripsi>",
                "Contoh: `/add 10 @friend1 @friend2 | Ujian modul 1`",
                "Bisa *reply* pesan user + `/add 10 | alasan`",
                "",
            ]
        )
    if role_can_open_presensi(role):
        lines.extend(
            [
                "*Presensi (buka/tutup)*",
                "/buka\\_presensi — Pilih kelas",
                "/tutup\\_presensi <id\\_sesi> — Tutup sesi",
                "",
            ]
        )
    if role == ROLE_LECTURER:
        lines.append(
            "*Dosen: isi Kelas yang diampu di /lengkapi.*"
        )
        lines.append("")
    if role_can_report(role) or role == ROLE_LECTURER:
        lines.extend(
            [
                "*Sesi & rekap hadir*",
                "/sesi — Sesi aktif"
                + (" _(hanya kelas diampu)_" if role == ROLE_LECTURER else ""),
                "/rekap\\_hadir <id\\_sesi> — Detail hadir & waktu",
                "",
            ]
        )
    if role_can_approve_profile(role):
        lines.extend(
            [
                "*Admin / Owner*",
                "/pending — Antrean ubah profil",
                "/admin\\_data <id> — Ubah profil user langsung (tanpa persetujuan)",
                "_Atau balas pesan user lalu_ `/admin_data`",
                "",
            ]
        )
    if role_can_view_sensitive_logs(role):
        lines.extend(
            [
                "/log — Audit & Agra (deskripsi)",
                "_Filter:_ `/log fakultas <id>` · `/log kelas <id>` · `/log nama <teks>`",
                "_Tanpa filter:_ ringkasan terbaru.",
                "",
            ]
        )
    if role_can_report(role):
        lines.extend(
            [
                "*Daftar pengguna*",
                "`/daftar fakultas <id>` · `/daftar jurusan <id>` · `/daftar kelas <id>`",
                "`/daftar admin` (owner & admin) · `/daftar staf` (staf biasa) · `/daftar dosen`",
                "_Hanya nama & username; data besar dipecah beberapa pesan._",
                "",
            ]
        )
    if role == ROLE_OWNER:
        lines.extend(
            [
                "*Owner*",
                "`/setrole <admin|lecturer|staff|student> @user …` atau reply + `/setrole <role>`",
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
    await update.message.reply_text(help_for_role(role), parse_mode="Markdown")


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
    # Saat cek profil orang lain, sembunyikan metadata internal moderator.
    show_raw = role_can_view_sensitive_logs(requester_role) and not is_target_lookup
    text = format_profile_card(
        row,
        profile=profile,
        agra=agra,
        show_internal=show_raw,
        user_role=row["role"] if row else ROLE_STUDENT,
    )
    await update.message.reply_text(text, parse_mode="Markdown")


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
        await update.message.reply_text(
            "Data awal sudah lengkap. Selanjutnya gunakan /ubah untuk perubahan."
        )
        return
    target_fields = miss

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
    await update.message.reply_text(
        "Pilih data yang ingin *diajukan* perubahannya (butuh persetujuan admin):",
        parse_mode="Markdown",
        reply_markup=_ubah_keyboard(fields_for_role(role)),
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
    rows.append(
        [InlineKeyboardButton("Selesai", callback_data="adgo:__done__"[:64])]
    )
    return InlineKeyboardMarkup(rows)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    data = q.data

    if data.startswith("o:"):
        from . import attendance

        await attendance.cb_open_presensi(update, context)
        return
    if data.startswith("h:"):
        from . import attendance

        await attendance.cb_hadir(update, context)
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
        if not row_ad or not role_can_report(row_ad["role"]):
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
                await q.edit_message_text("Pilih user dulu: /admin_data <id>.")
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
                    f"Kirim teks untuk *{fdef.label}* (user `{tid_target}`).",
                    parse_mode="Markdown",
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
                    f"Pilih *{fdef.label}* untuk `{tid_target}`:",
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
                return
            if fdef.type == "multi_choice" and fdef.choices_key:
                _multi_init(context, field_key, "ad", tprof)
                sel = context.user_data[MULTI_UD_KEY]["ids"]
                kb = keyboard_for_multi_choices(
                    field_key,
                    fdef.choices_key,
                    sel,
                    toggle_prefix="admlc",
                    done_prefix="admld",
                )
                await db.set_onboarding_step(conn, uid, f"MULTI_AD_LC:{field_key}")
                await q.edit_message_text(
                    f"Pilih *{fdef.label}* (multi) untuk `{tid_target}`.",
                    parse_mode="Markdown",
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
            await db.set_profile_partial(conn, tid_target, {field_key: choice_id})
            await _revalidate_filtered_choice_fields(conn, db, tid_target)
            await db.set_onboarding_step(conn, uid, None)
            await db.add_audit(
                conn, uid, "admin_profile_set", f"target={tid_target} key={field_key}"
            )
            lab = fdef.label if fdef else field_key
            await q.edit_message_text(f"✅ {lab} untuk `{tid_target}` disimpan.")
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
            kb = keyboard_for_multi_choices(
                field_key,
                fdef.choices_key,
                ids_set,
                toggle_prefix="admlc",
                done_prefix="admld",
            )
            await q.edit_message_text(
                f"Pilih *{fdef.label}* (multi) untuk `{tid_target}`.",
                parse_mode="Markdown",
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
                f"✅ {lab} ({len(ids_list)} pilihan) untuk `{tid_target}` disimpan."
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
                f"Pilih *{fdef.filter_by_field}* dulu di /lengkapi."
                if fdef.filter_by_field
                else "Tidak ada opsi."
            )
            await q.edit_message_text(hint, parse_mode="Markdown")
            return
        await q.edit_message_text(
            f"Pilih *{fdef.label}*:",
            parse_mode="Markdown",
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
            await q.edit_message_text("/lengkapi hanya untuk isi awal. Pakai /ubah.")
            return
        await db.set_onboarding_step(conn, uid, f"TEXT_LC:{field_key}")
        await q.edit_message_text(
            f"Kirim pesan teks untuk *{fdef.label}* (lengkapi).",
            parse_mode="Markdown",
        )
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
                f"Set *{fdef.filter_by_field}* dulu (lengkapi profil), atau tidak ada jurusan untuk fakultas ini."
                if fdef.filter_by_field
                else "Tidak ada opsi."
            )
            await q.edit_message_text(hint, parse_mode="Markdown")
            return
        await q.edit_message_text(
            f"Pilih nilai baru *{fdef.label}* (akan diajukan):",
            parse_mode="Markdown",
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
            f"Kirim teks baru untuk *{fdef.label}* (akan diajukan ke admin).",
            parse_mode="Markdown",
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
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            sel,
            toggle_prefix="mlc",
            done_prefix="mld",
        )
        await db.set_onboarding_step(conn, uid, f"MULTI_LC:{field_key}")
        await q.edit_message_text(
            f"Pilih satu atau lebih *{fdef.label}* (ketuk untuk centang, lalu *Selesai*).",
            parse_mode="Markdown",
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
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            sel,
            toggle_prefix="mec",
            done_prefix="med",
        )
        await db.set_onboarding_step(conn, uid, f"MULTI_EC:{field_key}")
        await q.edit_message_text(
            f"Pilih nilai baru *{fdef.label}*. Ajuan dikirim setelah *Selesai*.",
            parse_mode="Markdown",
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
            await q.edit_message_text("Sesi kedaluwarsa. Buka /lengkapi lagi.")
            _multi_clear(context)
            return
        m = context.user_data.get(MULTI_UD_KEY)
        if not m or m.get("field") != field_key or m.get("flow") != "lc":
            await q.edit_message_text("Sesi kedaluwarsa. Buka /lengkapi lagi.")
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
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            ids,
            toggle_prefix="mlc",
            done_prefix="mld",
        )
        await q.edit_message_text(
            f"Pilih satu atau lebih *{fdef.label}* (ketuk untuk centang, lalu *Selesai*).",
            parse_mode="Markdown",
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
            await q.edit_message_text("/lengkapi sudah ditutup. Gunakan /ubah.")
            _multi_clear(context)
            return
        if not step.startswith("MULTI_LC:") or step.split(":", 1)[1] != field_key:
            await q.answer()
            await q.edit_message_text("Sesi kedaluwarsa. Buka /lengkapi lagi.")
            _multi_clear(context)
            return
        if not m or m.get("field") != field_key or m.get("flow") != "lc":
            await q.answer()
            await q.edit_message_text("Sesi kedaluwarsa. Buka /lengkapi lagi.")
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
        _multi_clear(context)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        await q.edit_message_text(
            f"✅ {lab} disimpan ({len(ids_list)} pilihan)."
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
            await q.edit_message_text("Sesi kedaluwarsa. Buka /ubah lagi.")
            _multi_clear(context)
            return
        m = context.user_data.get(MULTI_UD_KEY)
        if not m or m.get("field") != field_key or m.get("flow") != "ec":
            await q.edit_message_text("Sesi kedaluwarsa. Buka /ubah lagi.")
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
        kb = keyboard_for_multi_choices(
            field_key,
            fdef.choices_key,
            ids,
            toggle_prefix="mec",
            done_prefix="med",
        )
        await q.edit_message_text(
            f"Pilih nilai baru *{fdef.label}* (bisa banyak). Ajuan dikirim setelah *Selesai*.",
            parse_mode="Markdown",
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
            await q.edit_message_text("Sesi kedaluwarsa. Buka /ubah lagi.")
            _multi_clear(context)
            return
        if not m or m.get("field") != field_key or m.get("flow") != "ec":
            await q.answer()
            await q.edit_message_text("Sesi kedaluwarsa. Buka /ubah lagi.")
            _multi_clear(context)
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        ids_list = sorted(m["ids"])
        if fdef and fdef.required and not ids_list:
            await q.answer("Pilih minimal satu opsi.", show_alert=True)
            return
        await q.answer()
        rid = await db.add_profile_request(conn, uid, {field_key: ids_list})
        _multi_clear(context)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await q.edit_message_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin."
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
            await q.edit_message_text("/lengkapi sudah ditutup. Gunakan /ubah.")
            return
        if not step.startswith("PICK_LC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text("Sesi kedaluwarsa. Buka /lengkapi lagi.")
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        prof_before = profile_from_row(step_row) if step_row else {}
        if fdef and fdef.filter_by_field and not is_choice_allowed_for_profile(
            fdef, prof_before, choice_id
        ):
            await q.edit_message_text(
                "Pilihan tidak cocok dengan data profil (mis. fakultas). Buka /lengkapi lagi."
            )
            return
        await db.set_profile_partial(conn, uid, {field_key: choice_id})
        await _mark_lengkapi_done_if_complete(conn, db, uid)
        await _revalidate_filtered_choice_fields(conn, db, uid)
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_direct_update", field_key)
        lab = fdef.label if fdef else field_label_for_key(field_key)
        await q.edit_message_text(f"✅ {lab} disimpan.")
        return

    if data.startswith("ec:"):
        await q.answer()
        _, field_key, choice_id = data.split(":", 2)
        step_row = await user_row(conn, db, uid)
        step = (step_row["onboarding_step"] or "") if step_row else ""
        if not step.startswith("PICK_EC:") or step.split(":", 1)[1] != field_key:
            await q.edit_message_text("Sesi kedaluwarsa. Buka /ubah lagi.")
            return
        fdef = next((x for x in PROFILE_FIELDS if x.key == field_key), None)
        prof_before = profile_from_row(step_row) if step_row else {}
        if fdef and fdef.filter_by_field and not is_choice_allowed_for_profile(
            fdef, prof_before, choice_id
        ):
            await q.edit_message_text(
                "Pilihan tidak valid untuk fakultas kamu saat ini. Perbarui fakultas dulu jika perlu."
            )
            return
        rid = await db.add_profile_request(conn, uid, {field_key: choice_id})
        await db.set_onboarding_step(conn, uid, None)
        await db.add_audit(conn, uid, "profile_change_request", f"id={rid}")
        await q.edit_message_text(
            "✅ Pengajuan perubahan dikirim. Menunggu persetujuan admin."
        )
        await _notify_moderators_profile(context, db, conn, rid, uid, {field_key: choice_id})
        return

    if data.startswith("a:"):
        await q.answer()
        parts = data.split(":")
        if len(parts) != 3:
            return
        _, rid_s, dec = parts
        row_u = await user_row(conn, db, uid)
        if not row_u or not role_can_approve_profile(row_u["role"]):
            await q.edit_message_text("Tidak diizinkan.")
            return
        ok, tid, proposed = await db.resolve_profile_request(
            conn, int(rid_s), approve=(dec == "1"), decided_by=uid
        )
        if not ok:
            await q.edit_message_text("Permintaan tidak tersedia.")
            return
        await db.add_audit(
            conn,
            uid,
            "profile_request_decided",
            f"id={rid_s} approve={dec} target={tid}",
        )
        status = "disetujui" if dec == "1" else "ditolak"
        original_text = q.message.text or f"Pengajuan #{rid_s}"
        await q.edit_message_text(
            f"{original_text}\n\nStatus: {status}."
        )
        if tid and dec == "1":
            await _revalidate_filtered_choice_fields(conn, db, tid)
        if tid:
            try:
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"Perubahan profil kamu *{status}*.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.warning("notify user fail: %s", e)
        if tid and dec == "1":
            try:
                nu = await user_row(conn, db, tid)
                if nu and missing_required_fields(
                    profile_from_row(nu), nu["role"]
                ):
                    await context.bot.send_message(
                        chat_id=tid,
                        text=(
                            "Beberapa field (mis. jurusan) dikosongkan karena tidak cocok dengan fakultas. "
                            "Lengkapi lagi dengan /lengkapi."
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
        f"Dari: `{proposer_id}` @{un}\n"
        f"Data awal: `{before_preview}`\n"
        f"Usulan: `{preview}`"
    )
    for mid in mods:
        if mid == proposer_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=mid, text=text, parse_mode="Markdown", reply_markup=kb
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
    if not row or not role_can_add_agra(row["role"]):
        await update.message.reply_text("Kamu tidak punya akses menambah Agra.")
        return

    parsed = parse_add_command(update.message)
    if not parsed:
        await update.message.reply_text(
            "Format: `/add <angka> @user … | <deskripsi>` atau reply pesan user lalu "
            "`/add <angka> | <deskripsi>`",
            parse_mode="Markdown",
        )
        return

    extra_ids = await db.find_ids_by_usernames(conn, parsed.mention_usernames)
    targets = set(parsed.target_ids) | set(extra_ids)
    if not targets:
        await update.message.reply_text(
            "Sebutkan user dengan @mention, text mention, atau reply pesannya."
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
        full_name = (
            prof.get("full_name")
            or f"{urow['first_name'] or ''} {urow['last_name'] or ''}".strip()
            or (f"@{urow['username']}" if urow["username"] else str(tid))
        )
        lines.append(f"→ {full_name}") # (total {new_total})
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"Kamu menerima *{parsed.amount}* Agra.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await db.add_audit(conn, actor, "agra_add", f"targets={targets} amount={parsed.amount}")
    summary = "\n".join(lines)
    await update.message.reply_text(
        f"✅ *{parsed.amount} Agra* berhasil dicatat.\n\nPenerima:\n{summary}",
        parse_mode="Markdown",
    )


async def cmd_admin_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    actor = update.effective_user.id
    row = await user_row(conn, db, actor)
    if not row or not role_can_report(row["role"]):
        await update.message.reply_text("Hanya admin atau owner.")
        return
    msg = update.message
    parts = (msg.text or "").split()
    target_tid: int | None = None
    if len(parts) >= 2 and parts[1].isdigit():
        target_tid = int(parts[1])
    elif msg.reply_to_message and msg.reply_to_message.from_user:
        target_tid = msg.reply_to_message.from_user.id
    if not target_tid:
        await update.message.reply_text(
            "Balas pesan user yang ingin diedit, atau:\n"
            "`/admin_data <telegram_id>`",
            parse_mode="Markdown",
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
        f"Edit profil `{target_tid}` (@{un}). "
        f"Pilih field — tersimpan langsung, tanpa persetujuan:",
        parse_mode="Markdown",
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
    for name, uname, tid in entries:
        dn = _daftar_clean_display(name)
        prefix = f"`{tid}` " if show_telegram_id else ""
        if uname:
            lines.append(f"{prefix}{dn} — @{uname}")
        else:
            lines.append(f"{prefix}{dn} — (tanpa username)")
    return lines


async def _reply_daftar_chunks(
    update: Update,
    title: str,
    lines: list[str],
    *,
    max_lines: int = 40,
    max_chars: int = 3400,
    pause_sec: float = 0.45,
    parse_mode: str | None = None,
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
        await update.message.reply_text(f"{head}\n\n{body}", parse_mode=parse_mode)
        if i < total - 1:
            await asyncio.sleep(pause_sec)


async def cmd_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not role_can_report(row["role"]):
        await update.message.reply_text("Hanya admin atau owner.")
        return
    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Daftar pengguna (nama + username)\n\n"
            "/daftar id fakultas <id>\n"
            "/daftar id jurusan <id>\n"
            "/daftar id kelas <id>\n"
            "/daftar id admin\n"
            "/daftar id staf\n"
            "/daftar id dosen\n"
            "/daftar fakultas <id>\n"
            "/daftar jurusan <id>\n"
            "/daftar kelas <id>\n"
            "/daftar admin — owner & admin\n"
            "/daftar staf — staf biasa (bukan dosen)\n"
            "/daftar dosen\n\n"
            "Data panjang otomatis dipecah ke beberapa pesan (~40 baris tiap pesan, "
            "jeda singkat antarpesan mengurangi risiko flood limit Telegram)."
        )
        return
    show_telegram_id = False
    kind_idx = 1
    if len(parts) >= 3 and parts[1].lower() == "id":
        show_telegram_id = True
        kind_idx = 2
    kind = parts[kind_idx].lower() if len(parts) > kind_idx else ""
    cur = await conn.execute(
        """
        SELECT telegram_id, username, first_name, last_name, role, profile_json
        FROM users
        ORDER BY LOWER(COALESCE(first_name, '')), telegram_id
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

    if kind == "admin":
        title = "Daftar Petinggi"
        for r in all_rows:
            if r["role"] in (ROLE_OWNER, ROLE_ADMIN):
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "staf":
        title = "Daftar staf (non-dosen)"
        for r in all_rows:
            if r["role"] == ROLE_STAFF:
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "dosen":
        title = "Daftar dosen"
        for r in all_rows:
            if r["role"] == ROLE_LECTURER:
                p = json.loads(r["profile_json"] or "{}")
                push_row(r, p)
    elif kind == "fakultas" and len(parts) > kind_idx + 1:
        fid = parts[kind_idx + 1]
        title = f"Daftar — fakultas {fid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            if p.get("faculty") == fid:
                push_row(r, p)
    elif kind == "jurusan" and len(parts) > kind_idx + 1:
        mid = parts[kind_idx + 1]
        title = f"Daftar — jurusan {mid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            if p.get("major") == mid:
                push_row(r, p)
    elif kind == "kelas" and len(parts) > kind_idx + 1:
        cid = parts[kind_idx + 1]
        title = f"Daftar — kelas {cid}"
        for r in all_rows:
            p = json.loads(r["profile_json"] or "{}")
            enrolled = normalize_multi_choice_value(p.get("class_enrolled"))
            teaching = normalize_multi_choice_value(p.get("teaching_classes"))
            if cid in enrolled or cid in teaching:
                push_row(r, p)
    else:
        await update.message.reply_text(
            "Format tidak dikenali. Ketik /daftar untuk bantuan singkat."
        )
        return

    matching.sort(key=lambda x: x[0].lower())
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
        parse_mode="Markdown" if show_telegram_id else None,
    )


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
            "`/setrole <admin|lecturer|staff|student> @user1 @user2`\n"
            "atau balas pesan seseorang lalu `/setrole <role>`\n\n"
            "Owner tetap hanya satu (di .env); tidak bisa set owner ke orang lain.",
            parse_mode="Markdown",
        )
        return
    role = parsed.role
    if role not in (
        ROLE_OWNER,
        ROLE_ADMIN,
        ROLE_LECTURER,
        ROLE_STAFF,
        ROLE_STUDENT,
    ):
        await update.message.reply_text(
            "Role tidak dikenal. Gunakan admin, lecturer, staff, atau student."
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
        lines_out.append(f"• {full_name} → {role_display(role)}")
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"Peran kamu diubah menjadi: *{role_display(role)}*",
                parse_mode="Markdown",
            )
        except Exception:
            pass
    await update.message.reply_text(
        "Set role selesai:\n" + "\n".join(lines_out)[:4000]
    )


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not role_can_approve_profile(row["role"]):
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
            f"#{p['id']} dari `{p['telegram_id']}`\n`{preview}`",
            parse_mode="Markdown",
            reply_markup=kb,
        )


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, update.effective_user.id)
    if not row or not role_can_view_sensitive_logs(row["role"]):
        await update.message.reply_text("Hanya admin/owner.")
        return
    text_raw = (update.message.text or "").strip()
    parts = text_raw.split()
    faculty_id = class_id = name_sub = None
    if len(parts) >= 3 and parts[1].lower() == "fakultas":
        faculty_id = parts[2]
    elif len(parts) >= 3 and parts[1].lower() == "kelas":
        class_id = parts[2]
    elif len(parts) >= 3 and parts[1].lower() == "nama":
        name_sub = " ".join(parts[2:])
    elif len(parts) > 1:
        await update.message.reply_text(
            "*Format filter /log:*\n"
            "`/log` — ringkasan terbaru\n"
            "`/log fakultas <id>` — contoh: `fmipa`\n"
            "`/log kelas <id_kelas>`\n"
            "`/log nama <potongan nama>`",
            parse_mode="Markdown",
        )
        return

    filtered = faculty_id is not None or class_id is not None or name_sub is not None
    if filtered:
        ids = await db.user_ids_matching_profile_filter(
            conn,
            faculty_id=faculty_id,
            class_id=class_id,
            name_substring=name_sub,
        )
        if not ids:
            await update.message.reply_text("Tidak ada user yang cocok dengan filter.")
            return
        audit_rows = await db.audit_log_for_actors(conn, ids, limit=20)
        agra_rows = await db.agra_ledger_for_targets(conn, ids, limit=15)
        hdr = []
        if faculty_id:
            hdr.append(f"fakultas `{faculty_id}`")
        if class_id:
            hdr.append(f"kelas `{class_id}`")
        if name_sub:
            hdr.append(f"nama `{name_sub}`")
        lines = [f"*Log* (filter: {', '.join(hdr)})", ""]
    else:
        cur = await conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 15",
        )
        audit_rows = await cur.fetchall()
        agra_rows = await db.agra_report(conn, limit=8)
        lines = ["*Log audit (15 terakhir)*", ""]

    lines.append("*Audit*")
    if not audit_rows:
        lines.append("_Kosong._")
    else:
        for r in audit_rows:
            ts = format_local_time(r["created_at"])
            det = (r["detail"] or "")[:120]
            lines.append(f"• `{ts}` `{r['action']}` — {det}")
    lines.extend(["", "*Agra (deskripsi — mod only)*"])
    if not agra_rows:
        lines.append("_Kosong._")
    else:
        for g in agra_rows:
            ts = format_local_time(g["created_at"])
            lines.append(
                f"• `{ts}` →`{g['target_telegram_id']}` **{g['amount']}** — _{g['description'][:80]}_"
            )
    await update.message.reply_text(
        "\n".join(lines)[:4000], parse_mode="Markdown"
    )


async def cmd_top_agra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    conn = _conn(context)
    db = _db(context)
    cur = await conn.execute(
        """
        SELECT t.target_telegram_id, t.total, u.profile_json, u.first_name, u.username
        FROM (
            SELECT target_telegram_id, SUM(amount) AS total
            FROM agra_ledger
            GROUP BY target_telegram_id
            ORDER BY total DESC
            LIMIT 17
        ) t
        LEFT JOIN users u ON u.telegram_id = t.target_telegram_id
        """
    )
    rows = await cur.fetchall()
    lines = ["Top 17 Agra"]
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
            lines.append(f"{idx}. {r['total']} - {name}")
    await update.message.reply_text("\n".join(lines))
