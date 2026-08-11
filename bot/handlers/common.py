from __future__ import annotations

import json
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import (
    ROLE_ADMIN,
    ROLE_INTERNAL,
    ROLE_OWNER,
    ROLE_STUDENT,
    ROLE_BEM,
    ROLE_MABA,
)
from bot.settings import (
    CHOICES,
    PROFILE_DISPLAY_KEYS,
    PROFILE_FIELDS,
    AGRA_REWARD_LENGKAPI,
    FieldDef,
    choice_label,
    field_applies_to_role,
    multi_choice_labels,
)

if TYPE_CHECKING:
    import aiosqlite

    from bot.database import Database


def role_display(role: str) -> str:
    return {
        ROLE_OWNER: "Founder",
        ROLE_ADMIN: "Sekretaris",
        ROLE_INTERNAL: "Internal",
        ROLE_BEM: "BEM",
        ROLE_STUDENT: "Mahasiswa",
        ROLE_MABA: "Mahasiswa Baru",
    }.get(role, role)


async def user_row(conn: aiosqlite.Connection, db: Database, telegram_id: int):
    return await db.get_user(conn, telegram_id)


def profile_from_row(row) -> dict:
    if not row:
        return {}
    return json.loads(row["profile_json"] or "{}")


async def award_lengkapi_agra(conn: aiosqlite.Connection, db: Database, uid: int, field_key: str, profile_before: dict, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    # Hanya untuk field utama (bukan tambahan)
    excluded_fields = {"teaching_classes", "club_enrolled", "auto_class_enrolled"}
    if field_key in excluded_fields:
        return
        
    # Cek apakah field sebelumnya sudah terisi (berarti bukan isi pertama kali)
    val_before = profile_before.get(field_key)
    if val_before is not None and val_before != "" and val_before != []:
        return
        
    # Cek batas maksimal Agra yang sudah didapatkan dari /lengkapi (max 5)
    count = profile_before.get("__lengkapi_agra_count", 0)
    if count >= 5:
        return
        
    amount = AGRA_REWARD_LENGKAPI
    await db.add_agra(
        conn,
        target_id=uid,
        actor_id=uid,
        amount=amount,
        description=f"Melengkapi profil: {field_label_for_key(field_key)}",
        chat_id=chat_id,
        message_id=None,
    )
    await db.set_profile_partial(conn, uid, {"__lengkapi_agra_count": count + 1})
    
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎁 Kamu mendapatkan <b>{amount} Agra</b> karena telah mengisi <b>{field_label_for_key(field_key)}</b> perdana!"
        )
    except Exception:
        pass


def normalize_multi_choice_value(raw) -> list[str]:
    """Satu nilai string lama (choice tunggal) tetap didukung."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def classes_for_staff_faculty(faculty_id: str) -> list[str]:
    """ID kelas yang termasuk fakultas (lewat jurusan di choices), plus Kuliah Umum."""
    fid = (faculty_id or "").strip()
    if not fid:
        return []
    majors_in = {
        str(m["id"])
        for m in CHOICES.get("majors", [])
        if str(m.get("faculty") or "") == fid
    }
    out: list[str] = []
    for item in CHOICES.get("classes", []):
        cid = str(item.get("id") or "")
        if not cid:
            continue
        if cid.startswith("umum_"):
            out.append(cid)
            continue
        if item.get("majors") in majors_in:
            out.append(cid)
    return list(dict.fromkeys(out))


def get_user_jabatans(profile: dict | None) -> list[str]:
    if not profile:
        return []
    return normalize_multi_choice_value(profile.get("position_detail"))


def is_dekan_profile(profile: dict | None) -> bool:
    return "d_dekan" in get_user_jabatans(profile)


def dean_faculty_id(profile: dict | None) -> str:
    return ((profile or {}).get("staff_faculty") or "").strip()


def user_in_dean_faculty_scope(p: dict, faculty_id: str) -> bool:
    """User muncul di /daftar saat difilter dekan fakultas ini."""
    fid = (faculty_id or "").strip()
    if not fid:
        return False
    if (p.get("staff_faculty") or "").strip() == fid:
        return True
    if (p.get("faculty") or "").strip() == fid:
        return True
    fac_classes = set(classes_for_staff_faculty(fid))
    if not fac_classes:
        return False
    teaching = set(normalize_multi_choice_value(p.get("teaching_classes")))
    if teaching & fac_classes:
        return True
    enrolled = set(normalize_multi_choice_value(p.get("class_enrolled")))
    if enrolled & fac_classes:
        return True
    return False


def can_daftar_as_dean(role: str, profile: dict | None) -> bool:
    if role in (ROLE_OWNER, ROLE_ADMIN):
        return True
    return is_dekan_profile(profile) and bool(dean_faculty_id(profile))


def is_lecturer_profile(profile: dict | None) -> bool:
    jabs = get_user_jabatans(profile)
    return "d_dosen" in jabs or "d_guru_besar" in jabs or "d_coach" in jabs


def lecturer_class_ids(profile: dict | None) -> list[str]:
    if not profile:
        return []
    jabs = get_user_jabatans(profile)
    ids = []
    if "d_dosen" in jabs or "d_guru_besar" in jabs:
        ids.extend(normalize_multi_choice_value(profile.get("teaching_classes")))
    if "d_coach" in jabs:
        ids.extend(normalize_multi_choice_value(profile.get("club_enrolled")))
    return list(dict.fromkeys(ids))


def user_in_lecturer_scope(p: dict, class_ids: list[str]) -> bool:
    if not class_ids:
        return False
    enrolled = set(normalize_multi_choice_value(p.get("class_enrolled")))
    teaching = set(normalize_multi_choice_value(p.get("teaching_classes")))
    club_enrolled = set(normalize_multi_choice_value(p.get("club_enrolled")))
    target_classes = set(class_ids)
    return bool((enrolled | teaching | club_enrolled) & target_classes)


def can_daftar_as_lecturer(role: str, profile: dict | None) -> bool:
    if role in (ROLE_OWNER, ROLE_ADMIN):
        return True
    return is_lecturer_profile(profile) and bool(lecturer_class_ids(profile))


def presence_allowed_class_ids(role: str, profile: dict | None) -> list[str] | None:
    """None = boleh semua kelas (admin/owner). List kosong = tidak ada akses."""
    p = profile or {}
    if role in (ROLE_OWNER, ROLE_ADMIN):
        return None
    jabatans = get_user_jabatans(p)
    ids = []
    has_access = False
    
    if "d_dosen" in jabatans or "d_guru_besar" in jabatans:
        has_access = True
        ids.extend(normalize_multi_choice_value(p.get("teaching_classes")))
    if "d_coach" in jabatans:
        has_access = True
        ids.extend(normalize_multi_choice_value(p.get("club_enrolled")))
    if "d_dekan" in jabatans and dean_faculty_id(p):
        has_access = True
        ids.extend(classes_for_staff_faculty(dean_faculty_id(p)))
    if "d_sekre" in jabatans:
        has_access = True
        ids.append("staff_auto")
        
    if has_access:
        return list(dict.fromkeys(ids))
    return []


def can_manage_agra(role: str, profile: dict | None) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)



def can_assign_roles(role: str, profile: dict | None) -> bool:
    return role == ROLE_OWNER


def can_approve_profile(role: str, profile: dict | None) -> bool:
    if role in (ROLE_OWNER, ROLE_ADMIN): return True
    return "d_umum_sdm" in get_user_jabatans(profile)


def can_view_sensitive_logs(role: str, profile: dict | None) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def can_report(role: str, profile: dict | None) -> bool:
    if role in (ROLE_OWNER, ROLE_ADMIN): return True
    return "d_dekan" in get_user_jabatans(profile)


def can_tag_all(role: str, profile: dict | None) -> bool:
    if role in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL, ROLE_BEM): return True
    jabatans = get_user_jabatans(profile)
    return "d_umum_admin" in jabatans or "d_dekan" in jabatans or "d_dosen" in jabatans or "d_guru_besar" in jabatans or "d_coach" in jabatans


def field_label_for_key(field_key: str) -> str:
    fd = next((f for f in PROFILE_FIELDS if f.key == field_key), None)
    return fd.label if fd else field_key.replace("_", " ").title()


def fields_for_role(role: str, profile: dict | None = None) -> list[FieldDef]:
    return [
        f
        for f in PROFILE_FIELDS
        if field_applies_to_role(f, role, profile) and f.key != "student_id" #yg baru and f.key != "student_id"
    ]


def display_keys_for_role(role: str, profile: dict | None = None) -> list[str]:
    out: list[str] = []
    for key in PROFILE_DISPLAY_KEYS:
        if key in ("telegram_name", "username"):
            continue
        if key in ("role", "agra_total"):
            out.append(key)
            continue
        fd = next((f for f in PROFILE_FIELDS if f.key == key), None)
        if fd:
            if field_applies_to_role(fd, role, profile):
                out.append(key)
        else:
            if key in ("total_sks", "auto_class_enrolled") and role not in (ROLE_STUDENT, ROLE_BEM):
                continue
            if key == "position" and role not in (ROLE_OWNER, ROLE_ADMIN, ROLE_INTERNAL):
                continue
            if key == "maba_group" and role != ROLE_MABA:
                continue
            out.append(key)
    return out


def optional_fields_still_open(profile: dict, role: str) -> list[FieldDef]:
    """Field opsional yang masih perlu ditawarkan di /lengkapi.

    Untuk ``multi_choice`` opsional, jika key belum ada di profil berarti user belum
    pernah menyelesaikan alur simpan (termasuk memilih nol opsi). Setelah disimpan,
    key ada (mis. list kosong) dan tidak ditampilkan lagi.
    """
    out: list[FieldDef] = []
    for f in fields_for_role(role, profile):
        if f.required:
            continue
        if f.type == "multi_choice":
            if f.key not in profile:
                out.append(f)
            continue
        v = profile.get(f.key)
        if f.type == "choice":
            if v is None or (isinstance(v, str) and not str(v).strip()):
                out.append(f)
            continue
        if v is None or (isinstance(v, str) and not str(v).strip()):
            out.append(f)
    return out


def missing_required_fields(profile: dict, role: str) -> list:
    miss = []
    for f in PROFILE_FIELDS:
        if not field_applies_to_role(f, role, profile):
            continue
        is_req = f.required
        if f.key == "club_enrolled":
            if role in ("student", "bem") or "d_coach" in get_user_jabatans(profile):
                is_req = True
        elif f.key == "teaching_classes":
            if "d_dosen" in get_user_jabatans(profile) or "d_guru_besar" in get_user_jabatans(profile):
                is_req = True
        
        if not is_req:
            continue
        v = profile.get(f.key)
        if f.type == "multi_choice":
            if not normalize_multi_choice_value(v):
                miss.append(f)
            continue
        if v is None or (isinstance(v, str) and not v.strip()):
            miss.append(f)
    if is_dekan_profile(profile):
        sf = next((x for x in PROFILE_FIELDS if x.key == "staff_faculty"), None)
        if sf and field_applies_to_role(sf, role, profile):
            v = profile.get("staff_faculty")
            if v is None or (isinstance(v, str) and not str(v).strip()):
                if sf not in miss:
                    miss.append(sf)
    return miss


def format_profile_card(
    row,
    *,
    profile: dict,
    agra: int,
    show_internal: bool,
    user_role: str,
) -> str:
    lines: list[str] = ["📇 <b>Profil</b>"]
    if not row:
        lines.append("_Belum terdaftar._")
        return "\n".join(lines)

    def val_for_display(key: str) -> str:
        if key == "telegram_name":
            fn = row["first_name"] or ""
            ln = row["last_name"] or ""
            return (fn + " " + ln).strip() or "—"
        if key == "username":
            u = row["username"]
            return f"@{u}" if u else "—"
        if key == "full_name":
            raw = profile.get("full_name")
            if not raw:
                return "—"
            u = row["username"]
            if u:
                return f'<a href="https://t.me/{u}">{raw}</a>'
            return f'<a href="tg://user?id={row["telegram_id"]}">{raw}</a>'
        if key == "student_id":
            raw = profile.get("student_id")
            return f"<code>{raw}</code>" if raw else "—"
        if key == "role":
            return role_display(row["role"])
        if key == "maba_group":
            mg = profile.get("maba_group")
            return f"Kelompok {mg}" if mg else "—"
        if key == "agra_total":
            return f"{agra:,}".replace(",", ".")
        if key == "auto_class_enrolled":
            major = profile.get("major")
            auto = []
            for item in CHOICES.get("classes", []):
                cid = item.get("id")
                if str(cid).startswith("umum_"):
                    continue
                m = item.get("majors")
                if not m or m == major:
                    auto.append(cid)
            return multi_choice_labels("classes", auto) if auto else "—"
        if key == "position":
            raw = profile.get("position")
            if not raw:
                detail_raw = normalize_multi_choice_value(profile.get("position_detail"))
                positions = []
                for item in CHOICES.get("position_details", []):
                    if item.get("id") in detail_raw:
                        pos = item.get("position")
                        if pos and pos not in positions:
                            positions.append(pos)
                if positions:
                    pos_order = {item.get("id"): i for i, item in enumerate(CHOICES.get("positions", []))}
                    highest_pos = min(positions, key=lambda p: pos_order.get(p, 999))
                    return choice_label("positions", highest_pos)
                return "—"
            return choice_label("positions", raw)

        fdef = next((x for x in PROFILE_FIELDS if x.key == key), None)
        if not fdef:
            return str(profile.get(key, "—"))

        raw = profile.get(fdef.key)
        if fdef.type == "multi_choice" and fdef.choices_key:
            return multi_choice_labels(fdef.choices_key, normalize_multi_choice_value(raw))
        if fdef.type == "choice" and fdef.choices_key:
            return choice_label(fdef.choices_key, raw) if raw else "—"
        return str(raw) if raw else "—"

    labels = {
        "telegram_name": "Nama Telegram",
        "username": "Username",
        "role": "Status",
        "agra_total": "Total Agra",
        "total_sks": "Total SKS",
        "auto_class_enrolled": "Kelas",
        "position": "पदवी",
    }
    for key in display_keys_for_role(user_role, profile):
        label = labels.get(key)
        if not label:
            fd = next((x for x in PROFILE_FIELDS if x.key == key), None)
            label = fd.label if fd else key.replace("_", " ").title()
        lines.append(f"<b>{label}:</b> {val_for_display(key)}")

    return "\n".join(lines)


def keyboard_for_choices(
    field_key: str,
    choices_key: str,
    *,
    prefix: str = "lc",
    options: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    opts = options if options is not None else CHOICES.get(choices_key, [])
    rows = []
    row = []
    for i, item in enumerate(opts):
        cid = item.get("id", "")
        lab = str(item.get("label", cid))
        row.append(
            InlineKeyboardButton(
                lab, callback_data=f"{prefix}:{field_key}:{cid}"[:64]
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Batal / Kembali", callback_data="cancel_action")])
    return InlineKeyboardMarkup(rows)


def keyboard_for_multi_choices(
    field_key: str,
    choices_key: str,
    selected: set[str],
    *,
    toggle_prefix: str,
    done_prefix: str,
    options: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    opts = options if options is not None else CHOICES.get(choices_key, [])
    rows: list[list[InlineKeyboardButton]] = []
    for item in opts:
        cid = str(item.get("id", ""))
        lab = str(item.get("label", cid))
        mark = "✓ " if cid in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    mark + lab,
                    callback_data=f"{toggle_prefix}:{field_key}:{cid}"[:64],
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "Selesai — simpan pilihan",
                callback_data=f"{done_prefix}:{field_key}"[:64],
            ),
            InlineKeyboardButton("⬅️ Batal", callback_data="cancel_action"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def sync_roles_from_env(db: Database, conn: aiosqlite.Connection) -> None:
    from bot.settings import ADMIN_IDS, OWNER_ID

    await db.ensure_owner_role(conn)
    if not OWNER_ID:
        return
    row = await db.get_user(conn, OWNER_ID)
    if row:
        await db.set_role(conn, OWNER_ID, ROLE_OWNER)
    for aid in ADMIN_IDS:
        r = await db.get_user(conn, aid)
        if r and r["role"] not in (ROLE_OWNER,):
            await db.set_role(conn, aid, ROLE_ADMIN)


async def moderator_chat_ids(db: Database, conn: aiosqlite.Connection) -> set[int]:
    from bot.settings import ADMIN_IDS, OWNER_ID

    ids = set(await db.list_moderator_telegram_ids(conn))
    if OWNER_ID:
        ids.add(OWNER_ID)
    ids |= ADMIN_IDS
    return ids


def is_lecturer_or_above(role: str) -> bool:
    # Deprecated function, but keeping it empty logic or returning false
    # if it's imported dynamically somewhere else. Let's just return if it's owner/admin.
    return role in (ROLE_OWNER, ROLE_ADMIN)

async def build_maba_verification_text(context, user_id: int | None = None) -> tuple[str, bool]:
    from bot.settings import MABA_CH_IDS
    if not MABA_CH_IDS:
        return "", True
        
    text_verify = "Data berhasil disimpan.\n\n" \
                  "Tahap terakhir: Anda **diwajibkan** untuk bergabung/follow channel berikut:\n"
                  
    all_followed = True
    for i, ch_id in enumerate(MABA_CH_IDS, 1):
        try:
            chat = await context.bot.get_chat(ch_id)
            if chat.username:
                link = f"@{chat.username}"
            elif chat.invite_link:
                link = chat.invite_link
            else:
                invite = await context.bot.create_chat_invite_link(ch_id)
                link = invite.invite_link
        except Exception:
            link = "(Tidak dapat mengambil link otomatis. Pastikan bot adalah Admin di channel tersebut.)"
            
        status_icon = "❌"
        if user_id:
            try:
                member = await context.bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                if member.status not in ("left", "kicked"):
                    status_icon = "✅"
                else:
                    all_followed = False
            except Exception:
                all_followed = False
        else:
            all_followed = False
            
        text_verify += f"{i}. {link} {status_icon}\n"
        
    text_verify += "\nSetelah bergabung, tekan tombol **Verifikasi Kembali** di bawah ini."
    return text_verify, all_followed
