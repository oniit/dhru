"""Render KTM (PNG) dari template + cache LRU di memori."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.settings import ROOT, choice_label, multi_choice_labels

log = logging.getLogger(__name__)

TEMPLATE_PATH = ROOT / "assets" / "ktm.png"
FONT_PATH = ROOT / "assets" / "Recoleta-RegularDEMO.otf"

# Warna & posisi untuk template 1050×600 (`assets/ktm.png`).
# Template sudah berisi label "Nama :", "NIM :", … — di sini hanya nilai, di kolom kanan (setelah foto).
TEXT_COLOR = (18, 28, 48)
CARD_W, CARD_H = 1050, 600
# Awal kolom nilai (sejajar setelah titik dua pada label cetak template).
VALUE_X = 540
# Baris pertama (Nama) — sesuaikan vertikal dengan baris "Nama :" di PNG.
NAME_Y = 222
# Jarak vertikal antar baris isian (Nama → NIM → Jurusan → UKM → Agra).
LINE_STEP = 48
NAME_SIZE = 30
NIM_SIZE = 28
CLUB_SIZE = 24
CLUB_MAX_LINES = 4
AGRA_SIZE = 36
# Kotak tempel foto (x, y, w, h) relatif ke template 1050×600 — area putih kiri.
PHOTO_SLOT = (103, 145, 275, 367)
PHOTO_CORNER_RADIUS_FRAC = 0.11  # relatif ke min(w,h) slot

# Bump jika layout teks / foto diubah (cache lama tidak dipakai lagi).
_LAYOUT_VERSION = 3

_CACHE: OrderedDict[str, bytes] = OrderedDict()
_CACHE_MAX = 128


def _cache_key(telegram_id: int, payload: dict) -> str:
    raw = json.dumps(
        {"v": _LAYOUT_VERSION, "p": payload}, sort_keys=True, ensure_ascii=False
    )
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{telegram_id}:{h}"


def _cache_get(key: str) -> bytes | None:
    if key not in _CACHE:
        return None
    _CACHE.move_to_end(key)
    return _CACHE[key]


def _cache_put(key: str, value: bytes) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        log.warning("Font KTM tidak ditemukan, pakai default: %s", FONT_PATH)
        try:
            return ImageFont.truetype("arial.ttf", size=size)
        except OSError:
            return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0])


def _wrap_lines(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int
) -> list[str]:
    text = (text or "").strip() or "—"
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w]) if cur else w
        if _text_width(draw, trial, font) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
                if len(lines) >= max_lines:
                    break
            cur = [w]
            if _text_width(draw, w, font) > max_width:
                # kata sangat panjang: potong
                chunk = w
                while chunk and len(lines) < max_lines:
                    lo, hi = 1, len(chunk)
                    best = 1
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        part = chunk[:mid]
                        if _text_width(draw, part, font) <= max_width:
                            best = mid
                            lo = mid + 1
                        else:
                            hi = mid - 1
                    lines.append(chunk[:best])
                    chunk = chunk[best:]
                cur = []
                if len(lines) >= max_lines:
                    break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(lines) == max_lines and _text_width(draw, lines[-1] + " …", font) > max_width:
        lines[-1] = lines[-1][: max(3, len(lines[-1]) - 3)] + "…"
    return lines if lines else ["—"]


def _normalize_multi_choice(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def cache_payload_for_profile(profile: dict, agra: int) -> dict:
    club_ids = sorted(_normalize_multi_choice(profile.get("club_enrolled")))
    return {
        "full_name": (profile.get("full_name") or "").strip(),
        "student_id": (profile.get("student_id") or "").strip(),
        "major": (profile.get("major") or "").strip(),
        "club_ids": club_ids,
        "agra": int(agra),
        "ktm_photo_file_id": (profile.get("ktm_photo_file_id") or "").strip(),
    }


def _cover_resize(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    im = im.convert("RGBA")
    scale = max(tw / im.width, th / im.height)
    nw = max(1, int(im.width * scale))
    nh = max(1, int(im.height * scale))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def _paste_photo_slot(
    base: Image.Image, photo_bytes: bytes, sx: float, sy: float
) -> None:
    slot_x = int(PHOTO_SLOT[0] * sx)
    slot_y = int(PHOTO_SLOT[1] * sy)
    slot_w = max(1, int(PHOTO_SLOT[2] * sx))
    slot_h = max(1, int(PHOTO_SLOT[3] * sy))
    try:
        ph = Image.open(BytesIO(photo_bytes)).convert("RGBA")
    except OSError:
        log.warning("KTM: file foto tidak bisa dibuka sebagai gambar")
        return
    fitted = _cover_resize(ph, (slot_w, slot_h))
    mask = Image.new("L", (slot_w, slot_h), 0)
    mdraw = ImageDraw.Draw(mask)
    r = max(4, int(min(slot_w, slot_h) * PHOTO_CORNER_RADIUS_FRAC))
    mdraw.rounded_rectangle((0, 0, slot_w, slot_h), radius=r, fill=255)
    base.paste(fitted, (slot_x, slot_y), mask)


def render_ktm_png_bytes(
    *,
    telegram_id: int,
    profile: dict,
    agra: int,
    use_cache: bool = True,
    photo_bytes: bytes | None = None,
) -> bytes:
    payload = cache_payload_for_profile(profile, agra)
    key = _cache_key(telegram_id, payload)
    if use_cache:
        hit = _cache_get(key)
        if hit is not None:
            return hit

    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Template KTM tidak ada: {TEMPLATE_PATH}")

    im = Image.open(TEMPLATE_PATH).convert("RGBA")
    W, H = im.size
    # Skala jika template diganti ukuran (proporsional).
    sx = W / CARD_W
    sy = H / CARD_H
    if photo_bytes:
        _paste_photo_slot(im, photo_bytes, sx, sy)
    draw = ImageDraw.Draw(im)
    value_x = int(VALUE_X * sx)
    name_y0 = int(NAME_Y * sy)
    line_step = int(LINE_STEP * sy)
    margin_r = int(48 * sx)
    club_max_w = max(120, W - value_x - margin_r)

    font_name = _load_font(int(NAME_SIZE * sy))
    font_body = _load_font(int(NIM_SIZE * sy))
    font_small = _load_font(int(CLUB_SIZE * sy))
    font_agra = _load_font(int(AGRA_SIZE * sy))

    name = (payload["full_name"] or "—").strip() or "—"
    nim = (payload["student_id"] or "—").strip() or "—"
    major_label = choice_label("majors", payload["major"] or None)
    club_text = multi_choice_labels("clubs", payload["club_ids"]) if payload["club_ids"] else "—"
    agra_s = str(payload["agra"])

    # Nama (satu baris; potong jika melebihi lebar kolom kanan)
    max_name_w = W - value_x - margin_r
    if _text_width(draw, name, font_name) > max_name_w:
        while name and _text_width(draw, name + "…", font_name) > max_name_w:
            name = name[:-1]
        name = (name + "…") if name else "—"

    y = name_y0
    draw.text((value_x, y), name, font=font_name, fill=TEXT_COLOR)
    y += line_step
    draw.text((value_x, y), nim, font=font_body, fill=TEXT_COLOR)
    y += line_step
    draw.text((value_x, y), major_label, font=font_body, fill=TEXT_COLOR)
    y += line_step

    club_lines = _wrap_lines(draw, club_text, font_small, club_max_w, CLUB_MAX_LINES)
    line_h = max(int(CLUB_SIZE * sy * 1.25), int(20 * sy))
    for line in club_lines:
        draw.text((value_x, y), line, font=font_small, fill=TEXT_COLOR)
        y += line_h
    y += int(6 * sy)
    draw.text((value_x, y), agra_s, font=font_agra, fill=TEXT_COLOR)

    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    out = buf.getvalue()
    if use_cache:
        _cache_put(key, out)
    return out
