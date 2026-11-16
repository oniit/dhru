"""Generator gambar Ijazah Kelulusan Shishya (PNG) menggunakan Pillow."""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.graduation_excel import StudentGraduationData
from bot.settings import ROOT

log = logging.getLogger(__name__)

TEMPLATE_PATH = ROOT / "assets" / "ijazah.png"
FONT_OPEN_SERIF_DIR = ROOT / "assets" / "Open_Serif"
FONT_OPEN_SERIF_PATH = FONT_OPEN_SERIF_DIR / "OpenSerif-Book.ttf"

FONT_CINZEL_DIR = ROOT / "assets" / "Cinzel"
FONT_CINZEL_BOLD_PATH = FONT_CINZEL_DIR / "Cinzel-Bold.otf"

# Warna teks
NAVY = (19, 50, 91, 255)  # #13325B
WHITE = (255, 255, 255, 255)

# Slot pasfoto di ijazah (x, y, w, h)
PHOTO_SLOT = (294, 567, 132, 171)

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


def get_degree_title(fakultas: str, jurusan: str = "") -> str:
    """Gelar akademik resmi: FMIPA -> Sarjana Sains (S.Si.), FIB -> Sarjana Seni (S.Sn.)."""
    f = (fakultas or "").strip().lower()
    j = (jurusan or "").strip().lower()

    if any(k in f for k in ["budaya", "fib", "seni", "sastra"]) or any(k in j for k in ["fotografi", "musik", "seni"]):
        return "Sarjana Seni (S.Sn.)"

    if any(k in f for k in ["matematika", "ipa", "mipa", "fmipa", "sains"]) or any(k in j for k in ["fisika", "kimia", "biologi", "matematika"]):
        return "Sarjana Sains (S.Si.)"

    return "Sarjana Sains (S.Si.)"


def render_ijazah_png(
    student: StudentGraduationData,
    photo_bytes: bytes | None = None,
) -> Image.Image:
    """Render ijazah kelulusan ke objek PIL Image."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template ijazah tidak ditemukan: {TEMPLATE_PATH}")

    base_im = Image.open(TEMPLATE_PATH).convert("RGBA")

    # Tempel pasfoto jika tersedia
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
            log.warning("Gagal menempelkan foto ke ijazah NIM %s: %s", student.nim, e)

    draw = ImageDraw.Draw(base_im)

    # 1. Nama Mahasiswa di Ijazah menggunakan Font CINZEL BOLD (Putih di dalam Kotak Biru Tua)
    # Box width = 418 px. Auto-shrink jika nama panjang.
    name_size = 28
    font_name = _load_font(FONT_CINZEL_BOLD_PATH, name_size)
    bbox = draw.textbbox((0, 0), student.nama, font=font_name)
    text_w = bbox[2] - bbox[0]
    while text_w > 390 and name_size > 12:
        name_size -= 1
        font_name = _load_font(FONT_CINZEL_BOLD_PATH, name_size)
        bbox = draw.textbbox((0, 0), student.nama, font=font_name)
        text_w = bbox[2] - bbox[0]

    draw.text((276, 342), student.nama, fill=WHITE, font=font_name, anchor="mm")

    # 2. NIM dan Tanggal Lahir menggunakan Font OPEN SERIF (Center di celah kosong baris template Y=388)
    font_open_12 = _load_font(FONT_OPEN_SERIF_PATH, 12)
    # Slot NIM: X=120 s.d 192 (center = 156)
    draw.text((165, 388), student.nim, fill=NAVY, font=font_open_12, anchor="mm")
    # Slot Tanggal Lahir: X=316 s.d 469 (center = 392, celah kosong sama rata)
    draw.text((401, 388), student.ttl, fill=NAVY, font=font_open_12, anchor="mm")

    # 3. Jurusan - Fakultas (Bold, dengan penambahan awalan 'Fakultas')
    fakultas_clean = (student.fakultas or "").strip()
    if fakultas_clean and not fakultas_clean.lower().startswith("fakultas"):
        fakultas_display = f"Fakultas {fakultas_clean}"
    else:
        fakultas_display = fakultas_clean

    if student.jurusan and fakultas_display:
        jurusan_fakultas = f"{student.jurusan} - {fakultas_display}"
    else:
        jurusan_fakultas = student.jurusan or fakultas_display or ""

    # 3. Jurusan - Fakultas menggunakan Font CINZEL BOLD (dengan penambahan awalan 'Fakultas')
    j_size = 18
    font_jurusan = _load_font(FONT_CINZEL_BOLD_PATH, j_size)
    bbox_j = draw.textbbox((0, 0), jurusan_fakultas, font=font_jurusan)
    while (bbox_j[2] - bbox_j[0]) > 420 and j_size > 10:
        j_size -= 1
        font_jurusan = _load_font(FONT_CINZEL_BOLD_PATH, j_size)
        bbox_j = draw.textbbox((0, 0), jurusan_fakultas, font=font_jurusan)

    draw.text((276, 445), jurusan_fakultas, fill=NAVY, font=font_jurusan, anchor="mm")

    # 4. Gelar Akademik Resmi menggunakan Font CINZEL BOLD
    font_gelar = _load_font(FONT_CINZEL_BOLD_PATH, 24)
    degree_title = get_degree_title(student.fakultas, student.jurusan)
    draw.text((276, 498), degree_title, fill=NAVY, font=font_gelar, anchor="mm")

    return base_im


def _cache_key(student: StudentGraduationData, photo_bytes: bytes | None) -> str:
    h_photo = hashlib.sha256(photo_bytes).hexdigest()[:16] if photo_bytes else "none"
    return f"{_LAYOUT_VERSION}:{student.nim}:{student.jurusan}:{student.fakultas}:{h_photo}"


def render_ijazah_png_bytes(
    student: StudentGraduationData,
    photo_bytes: bytes | None = None,
    use_cache: bool = True,
) -> bytes:
    """Render ijazah kelulusan langsung ke bytes PNG dengan cache in-memory."""
    key = _cache_key(student, photo_bytes)
    if use_cache and key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    im = render_ijazah_png(student=student, photo_bytes=photo_bytes)
    out = BytesIO()
    im.save(out, format="PNG")
    val = out.getvalue()

    if use_cache:
        _CACHE[key] = val
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)

    return val
