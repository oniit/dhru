"""Generator gambar Transkrip Nilai Shishya (PNG) menggunakan Pillow."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.graduation_excel import StudentGraduationData
from bot.settings import ROOT

log = logging.getLogger(__name__)

TEMPLATE_PATH = ROOT / "assets" / "transkrip.png"
FONT_DIR = ROOT / "assets" / "Open_Serif"
FONT_OPEN_SERIF_PATH = FONT_DIR / "OpenSerif-Book.ttf"

# Warna teks
NAVY = (19, 50, 91, 255)  # #13325B

# Slot pasfoto di transkrip (x, y, w, h)
PHOTO_SLOT = (72, 178, 101, 131)

# Koordinat baris mata kuliah akademik (Y center)
MK_ROW_Y = [399, 416, 433, 450]

# Koordinat baris UKM (Y center)
UKM_ROW_Y = [597, 614, 631]

# Cache font & LRU cache gambar
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_CACHE: OrderedDict[str, bytes] = OrderedDict()
_CACHE_MAX = 64
_LAYOUT_VERSION = 7


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (str(font_path), size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        f = ImageFont.truetype(str(font_path), size=size)
    except OSError:
        try:
            f = ImageFont.truetype("arial.ttf", size=size)
        except OSError:
            f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def render_transkrip_png(
    student: StudentGraduationData,
    photo_bytes: bytes | None = None,
) -> Image.Image:
    """Render transkrip nilai ke objek PIL Image."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template transkrip tidak ditemukan: {TEMPLATE_PATH}")

    base_im = Image.open(TEMPLATE_PATH).convert("RGBA")

    # Tempel foto jika tersedia
    if photo_bytes:
        try:
            photo = Image.open(BytesIO(photo_bytes)).convert("RGBA")
            tw, th = PHOTO_SLOT[2], PHOTO_SLOT[3]

            pw, ph = photo.size
            scale = max(tw / pw, th / ph)
            nw, nh = int(pw * scale), int(ph * scale)
            photo_scaled = photo.resize((nw, nh), Image.Resampling.LANCZOS)
            x_left = (nw - tw) // 2
            y_top = (nh - th) // 2
            photo_cropped = photo_scaled.crop((x_left, y_top, x_left + tw, y_top + th))

            base_im.paste(photo_cropped, (PHOTO_SLOT[0], PHOTO_SLOT[1]))
        except Exception as e:
            log.warning("Gagal menempelkan foto ke transkrip NIM %s: %s", student.nim, e)

    draw = ImageDraw.Draw(base_im)

    font_open_10 = _load_font(FONT_OPEN_SERIF_PATH, 10)
    font_open_11 = _load_font(FONT_OPEN_SERIF_PATH, 11)
    font_open_12 = _load_font(FONT_OPEN_SERIF_PATH, 12)
    font_open_13 = _load_font(FONT_OPEN_SERIF_PATH, 13)

    # 1. Identitas Mahasiswa (Generasi/NIM regular, Nama dibuat Bold)
    draw.text((325, 204), f"{student.generasi} / {student.nim}", fill=NAVY, font=font_open_12)

    # Auto-shrink nama jika melebihi batas kolom (X=325 sampai X=485, max 160px)
    name_size = 12
    font_name = _load_font(FONT_OPEN_SERIF_PATH, name_size)
    bbox_name = draw.textbbox((0, 0), student.nama, font=font_name, stroke_width=0.4)
    while (bbox_name[2] - bbox_name[0]) > 160 and name_size > 8:
        name_size -= 1
        font_name = _load_font(FONT_OPEN_SERIF_PATH, name_size)
        bbox_name = draw.textbbox((0, 0), student.nama, font=font_name, stroke_width=0.4)

    draw.text((325, 224), student.nama, fill=NAVY, font=font_name, stroke_width=0.4, stroke_fill=NAVY)
    draw.text((325, 245), student.ttl, fill=NAVY, font=font_open_12)
    draw.text((325, 266), student.jurusan, fill=NAVY, font=font_open_12)
    draw.text((325, 287), student.fakultas, fill=NAVY, font=font_open_12)

    # 2. Tabel Mata Kuliah Akademik (Font Open Serif)
    for idx, course in enumerate(student.courses[:4]):
        y = MK_ROW_Y[idx]
        draw.text((92, y), course.kode, fill=NAVY, font=font_open_10, anchor="mm")
        draw.text((138, y), course.nama, fill=NAVY, font=font_open_10, anchor="lm")
        draw.text((376, y), str(course.sks), fill=NAVY, font=font_open_10, anchor="mm")
        draw.text((425, y), course.nilai, fill=NAVY, font=font_open_11, anchor="mm")
        draw.text((470, y), course.ip, fill=NAVY, font=font_open_10, anchor="mm")

    # 3. IPK dan Predikat (IPK & Predikat Bold)
    draw.text((470, 468), student.ipk, fill=NAVY, font=font_open_11, anchor="mm", stroke_width=0.4, stroke_fill=NAVY)

    predikat_label = student.predikat if student.predikat and student.predikat != "-" else "LULUS"
    pred_size = 13
    font_pred = _load_font(FONT_OPEN_SERIF_PATH, pred_size)
    bbox_pred = draw.textbbox((0, 0), predikat_label, font=font_pred, stroke_width=0.4)
    while (bbox_pred[2] - bbox_pred[0]) > 122 and pred_size > 8:
        pred_size -= 1
        font_pred = _load_font(FONT_OPEN_SERIF_PATH, pred_size)
        bbox_pred = draw.textbbox((0, 0), predikat_label, font=font_pred, stroke_width=0.4)
    draw.text((421, 496), predikat_label, fill=NAVY, font=font_pred, anchor="mm", stroke_width=0.4, stroke_fill=NAVY)

    # 4. Tabel Unit Kegiatan Mahasiswa (UKM)
    for idx, club in enumerate(student.clubs[:3]):
        y = UKM_ROW_Y[idx]
        draw.text((60, y), club.nama, fill=NAVY, font=font_open_10, anchor="lm")
        draw.text((425, y), str(club.sks), fill=NAVY, font=font_open_10, anchor="mm")
        draw.text((471, y), club.nilai, fill=NAVY, font=font_open_11, anchor="mm")

    # 5. IKK (Bold)
    if student.ikk and student.ikk != "0,00":
        draw.text((471, 649), student.ikk, fill=NAVY, font=font_open_11, anchor="mm", stroke_width=0.4, stroke_fill=NAVY)

    return base_im


def _cache_key(student: StudentGraduationData, photo_bytes: bytes | None) -> str:
    h_photo = hashlib.sha256(photo_bytes).hexdigest()[:16] if photo_bytes else "none"
    return f"{_LAYOUT_VERSION}:{student.nim}:{student.ipk}:{student.predikat}:{h_photo}"


def render_transkrip_png_bytes(
    student: StudentGraduationData,
    photo_bytes: bytes | None = None,
    use_cache: bool = True,
) -> bytes:
    """Render transkrip nilai langsung ke bytes PNG dengan cache in-memory."""
    key = _cache_key(student, photo_bytes)
    if use_cache and key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    im = render_transkrip_png(student=student, photo_bytes=photo_bytes)
    out = BytesIO()
    im.save(out, format="PNG")
    val = out.getvalue()

    if use_cache:
        _CACHE[key] = val
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)

    return val
