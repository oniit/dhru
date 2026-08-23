"""Load env + YAML config. Edit config/*.yaml to change fields and dropdowns."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class FieldDef:
    key: str
    label: str
    type: str  # text | choice | multi_choice
    choices_key: str | None
    required: bool
    # Jika diisi (mis. faculty): hanya opsi yang punya `faculty: <id>` sama di choices.yaml
    filter_by_field: str | None = None
    # Jika None, field berlaku untuk semua peran. Contoh: roles: [student]
    roles: tuple[str, ...] | None = None


def _load_yaml(name: str) -> dict:
    path = ROOT / "config" / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_choices() -> dict[str, list[dict]]:
    data = _load_yaml("choices.yaml")
    out: dict[str, list[dict]] = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = v
    return out


def load_profile_fields() -> tuple[list[FieldDef], list[str]]:
    data = _load_yaml("profile_fields.yaml")
    raw_fields = data.get("fields") or []
    fields: list[FieldDef] = []
    for row in raw_fields:
        r = row.get("roles")
        roles_tuple: tuple[str, ...] | None = None
        if isinstance(r, list) and r:
            roles_tuple = tuple(str(x) for x in r)
        fields.append(
            FieldDef(
                key=row["key"],
                label=row.get("label", row["key"]),
                type=row.get("type", "text"),
                choices_key=row.get("choices_key"),
                required=bool(row.get("required", False)),
                filter_by_field=row.get("filter_by_field"),
                roles=roles_tuple,
            )
        )
    display = data.get("profile_display") or [f.key for f in fields]
    return fields, display


CHOICES = load_choices()
PROFILE_FIELDS, PROFILE_DISPLAY_KEYS = load_profile_fields()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)
GENERATION_CODE = os.environ.get("GENERATION_CODE", "01").strip()

_fg = os.environ.get("PETINGGI_GID", "").strip()
PETINGGI_GID = int(_fg) if _fg else None

_bc = os.environ.get("BACKUP_CH_ID", "").strip()
BACKUP_CH_ID = int(_bc) if _bc else None

_pc = os.environ.get("PRESENCE_CH_ID", "").strip()
PRESENCE_CH_ID = int(_pc) if _pc else None

_tc = os.environ.get("TASK_CH_ID", "").strip()
TASK_CH_ID = int(_tc) if _tc else None

_eg = os.environ.get("EDITOR_GID", "").strip()
EDITOR_GID = int(_eg) if _eg else None

_mc = os.environ.get("MENFESS_CH_ID", "").strip()
MENFESS_CH_ID = int(_mc) if _mc else None

_maba_chs = os.environ.get("MABA_CH_IDS", "").strip()
MABA_CH_IDS = [int(x.strip()) for x in _maba_chs.split(",") if x.strip()] if _maba_chs else []

_pendaftar_ch = os.environ.get("PENDAFTAR_CH_ID", "").strip()
PENDAFTAR_CH_ID = int(_pendaftar_ch) if _pendaftar_ch else None

_kelompok_gid = os.environ.get("KELOMPOK_GID", "").strip()
KELOMPOK_GID = int(_kelompok_gid) if _kelompok_gid else None

MABA_GROUP_LINK = os.environ.get("MABA_GROUP_LINK", "").strip()

# Agra Rewards Configuration
_rewards = _load_yaml("rewards.yaml")
AGRA_REWARD_CLASS_HADIR = int(_rewards.get("class_hadir", 25))
AGRA_REWARD_CLASS_IZIN = int(_rewards.get("class_izin", 10))
AGRA_REWARD_STAFF_AUTO = int(_rewards.get("staff_auto", 2))
AGRA_REWARD_LENGKAPI = int(_rewards.get("lengkapi", 15))
AGRA_REWARD_TUGAS = int(_rewards.get("tugas", 35))

_maba_gids = os.environ.get("MABA_GROUP_GIDS", "").strip()
MABA_GROUP_GIDS = [int(x.strip()) for x in _maba_gids.split(",") if x.strip()] if _maba_gids else []

MABA_GROUP_NAMES = {
    1: "Pramoerdita",
    2: "Nusapraja",
    3: "Candrakirana",
    4: "Purnawijaya",
}



def _parse_id_list(s: str | None) -> set[int]:
    if not s:
        return set()
    out: set[int] = set()
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


ADMIN_IDS = _parse_id_list(os.environ.get("ADMIN_IDS"))

# Legacy placeholder from spec — map to OWNER_ID in docs; runtime uses OWNER_ID + ADMIN_IDS


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID and OWNER_ID != 0


def is_admin_elevated(user_id: int) -> bool:
    return is_owner(user_id) or user_id in ADMIN_IDS


def choice_label(choices_key: str, choice_id: str | None) -> str:
    if not choice_id:
        return "—"
    for item in CHOICES.get(choices_key, []):
        if item.get("id") == choice_id:
            return str(item.get("label", choice_id))
    return choice_id


def filtered_choice_items(field_def: FieldDef, profile: dict) -> list[dict]:
    """Opsi untuk field choice/multi_choice; filter by `faculty` di tiap item jika filter_by_field di-set."""
    key = field_def.choices_key or ""
    raw = list(CHOICES.get(key, []))
    
    if key == "classes":
        pd = profile.get("position_detail")
        jabs = pd if isinstance(pd, list) else ([pd] if pd else [])
        is_gb = "d_guru_besar" in jabs
        filtered = []
        for item in raw:
            cid = str(item.get("id", ""))
            if is_gb and not cid.startswith("umum_"):
                continue
            if not is_gb and cid.startswith("umum_"):
                continue
            filtered.append(item)
        raw = filtered

    parent_key = field_def.filter_by_field
    if not parent_key:
        return raw
    parent_val = profile.get(parent_key)
    if not parent_val:
        return []
    out: list[dict] = []
    for item in raw:
        fac = item.get("faculty")
        if fac is None or fac == "":
            out.append(item)
        elif fac == parent_val:
            out.append(item)
    return out


def is_choice_allowed_for_profile(
    field_def: FieldDef, profile: dict, choice_id: str
) -> bool:
    allowed = {str(x.get("id")) for x in filtered_choice_items(field_def, profile)}
    return choice_id in allowed


def field_applies_to_role(field_def: FieldDef, role: str, profile: dict | None = None) -> bool:
    def has_jabatan(jab_id: str) -> bool:
        if not profile:
            return False
        pd = profile.get("position_detail")
        if isinstance(pd, list):
            return jab_id in pd
        return pd == jab_id

    if field_def.key == "staff_faculty":
        return has_jabatan("d_dekan")

    if field_def.key == "club_enrolled":
        if role in ("student", "bem"):
            return True
        if has_jabatan("d_coach"):
            return True
        return False
        
    if field_def.key == "teaching_classes":
        if has_jabatan("d_dosen") or has_jabatan("d_guru_besar"):
            return True
        return False

    if field_def.roles is None:
        return True
    return role in field_def.roles


def multi_choice_labels(choices_key: str, ids: list[str] | None) -> str:
    if not ids:
        return "—"
    order = [str(x.get("id")) for x in CHOICES.get(choices_key, [])]
    rank = {cid: i for i, cid in enumerate(order)}
    sorted_ids = sorted((str(i) for i in ids if i), key=lambda x: rank.get(x, 999))
    return ", ".join(choice_label(choices_key, i) for i in sorted_ids)
