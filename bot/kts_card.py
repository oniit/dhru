"""Render KTS (PNG) dari template + cache LRU di memori."""

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

TEMPLATE_PATH = ROOT / "assets" / "kts.png"
FONT_PATH = ROOT / "assets" / "Mukta/Mukta-Regular.ttf"
FONT_LIGHT_PATH = ROOT / "assets" / "Mukta/Mukta-Light.ttf"

# Warna & posisi untuk template 1050×600 (`assets/kts.png`).
# Template sudah berisi label "Nama :", "NIM :", … — di sini hanya nilai, di kolom kanan (setelah foto).
TEXT_COLOR = (18, 28, 48)
CARD_W, CARD_H = 1080, 1080
# Awal kolom nilai (sejajar setelah titik dua pada label cetak template).
VALUE_X = 520
# Posisi vertikal masing-masing baris
NAME_Y = 463
NIM_Y = 504
MAJOR_Y = 539
CLUB_Y = 580
AGRA_Y = 603
NAME_SIZE = 34
NIM_SIZE = 30
CLUB_SIZE = 24
CLUB_MAX_LINES = 4
AGRA_SIZE = 40
BEM_SIZE = 22
# Kotak tempel foto (x, y, w, h) relatif ke template 1080x1080
PHOTO_SLOT = (79, 380, 251, 325)
PHOTO_CORNER_RADIUS_FRAC = 0.05

# Bump jika layout teks / foto diubah (cache lama tidak dipakai lagi).
_LAYOUT_VERSION = 5

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


def _load_font(size: int, font_path: Path | str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fp = font_path or FONT_PATH
    try:
        return ImageFont.truetype(str(fp), size=size)
    except OSError:
        log.warning("Font KTS tidak ditemukan, pakai fallback: %s", fp)
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
        "bem_position": (profile.get("bem_position") or "").strip(),
        "photo_file_id": (profile.get("photo_file_id") or "").strip(),
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
        log.warning("KTS: file foto tidak bisa dibuka sebagai gambar")
        return
    fitted = _cover_resize(ph, (slot_w, slot_h))
    base.paste(fitted, (slot_x, slot_y))


def render_kts_png_bytes(
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
        raise FileNotFoundError(f"Template KTS tidak ada: {TEMPLATE_PATH}")

    im = Image.open(TEMPLATE_PATH).convert("RGBA")
    W, H = im.size
    # Skala jika template diganti ukuran (proporsional).
    sx = W / CARD_W
    sy = H / CARD_H
    
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if photo_bytes:
        _paste_photo_slot(overlay, photo_bytes, sx, sy)
    draw = ImageDraw.Draw(overlay)
    
    value_x = int(VALUE_X * sx)
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
    agra_s = f"{payload['agra']:,}".replace(",", ".")

    # Nama (satu baris; potong jika melebihi lebar kolom kanan)
    max_name_w = W - value_x - margin_r
    if _text_width(draw, name, font_name) > max_name_w:
        while name and _text_width(draw, name + "…", font_name) > max_name_w:
            name = name[:-1]
        name = (name + "…") if name else "—"

    # Nama
    y = int(NAME_Y * sy)
    draw.text((value_x, y), name, font=font_name, fill=TEXT_COLOR)
    
    # NIM
    y = int(NIM_Y * sy)
    draw.text((value_x, y), nim, font=font_body, fill=TEXT_COLOR)
    
    # Major
    y = int(MAJOR_Y * sy)
    draw.text((value_x, y), major_label, font=font_body, fill=TEXT_COLOR)
    
    # Club
    y = int(CLUB_Y * sy)
    club_lines = _wrap_lines(draw, club_text, font_small, club_max_w, CLUB_MAX_LINES)
    line_h = max(int(CLUB_SIZE * sy * 1.25), int(20 * sy))
    for line in club_lines:
        draw.text((value_x, y), line, font=font_small, fill=TEXT_COLOR)
        y += line_h
        
    # Agra
    y = int(AGRA_Y * sy)
    draw.text((value_x, y), agra_s, font=font_agra, fill=TEXT_COLOR)

    bem_pos_id = payload.get("bem_position")
    if bem_pos_id:
        from bot.settings import CHOICES
        bem_pos_item = next((x for x in CHOICES.get("bem_positions", []) if x.get("id") == bem_pos_id), None)
        if bem_pos_item:
            b_label = str(bem_pos_item.get("label", ""))
            b_detail = str(bem_pos_item.get("detail", ""))
            b_y = int(660 * sy)
            b_x = int(380 * sx)  # Lebih ke kiri dari value (VALUE_X=520)
            if b_label:
                # Kita gunakan font utama atau font light terserah, dengan warna teks gelap
                font_light = _load_font(int(BEM_SIZE * sy), font_path=FONT_LIGHT_PATH)
                draw.text((b_x, b_y), f"{b_label} — {b_detail}", font=font_light, fill=TEXT_COLOR)
                
    # Terapkan rotasi pada overlay teks & foto
    overlay = overlay.rotate(3.6, resample=Image.BICUBIC, center=(W//2, H//2))
    im.alpha_composite(overlay)

    buf = BytesIO()
    im.save(buf, format="PNG")
    out = buf.getvalue()
    if use_cache:
        _cache_put(key, out)
    return out
