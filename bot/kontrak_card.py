"""Render Kontrak (PNG) dari template + TTD."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageChops

from bot.settings import ROOT

log = logging.getLogger(__name__)

TEMPLATE_PATH = ROOT / "assets" / "kontrak.png"
FONT_PATH = ROOT / "assets" / "Mukta/Mukta-Regular.ttf"

# Koordinat perkiraan untuk template A4/Dokumen (misal 1240 x 1754 pixel)
CARD_W, CARD_H = 1240, 1754
TEXT_COLOR = (0, 0, 0)

# Posisi teks:
# (x, y) untuk Nama, Jabatan, Masa Kontrak
NAME_POS = (450, 600)
ROLE_POS = (450, 680)
PERIOD_POS = (450, 760)

TEXT_SIZE = 40

# Posisi kotak TTD di bagian bawah dokumen
TTD_SLOT = (750, 1300, 400, 250) # x, y, width, height


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        try:
            return ImageFont.truetype("arial.ttf", size=size)
        except OSError:
            return ImageFont.load_default()


def _paste_ttd_multiply(base: Image.Image, ttd_bytes: bytes, sx: float, sy: float) -> None:
    slot_x = int(TTD_SLOT[0] * sx)
    slot_y = int(TTD_SLOT[1] * sy)
    slot_w = int(TTD_SLOT[2] * sx)
    slot_h = int(TTD_SLOT[3] * sy)
    try:
        ttd = Image.open(BytesIO(ttd_bytes)).convert("RGB")
    except Exception:
        log.warning("Gagal memuat gambar TTD")
        return

    # Resize gambar TTD agar muat ke dalam kotak slot
    ttd.thumbnail((slot_w, slot_h), Image.Resampling.LANCZOS)
    
    # Posisikan di tengah slot
    paste_x = slot_x + (slot_w - ttd.width) // 2
    paste_y = slot_y + (slot_h - ttd.height) // 2
    
    # Ambil background dari base sebesar ukuran TTD
    base_crop = base.crop((paste_x, paste_y, paste_x + ttd.width, paste_y + ttd.height)).convert("RGB")
    
    # Kalikan (Multiply) untuk menghilangkan background putih TTD
    blended = ImageChops.multiply(base_crop, ttd)
    
    base.paste(blended, (paste_x, paste_y))


def render_kontrak_png_bytes(
    *,
    name: str,
    role_detail: str,
    period_str: str,
    ttd_bytes: bytes,
) -> bytes:
    if not TEMPLATE_PATH.is_file():
        # Buat gambar putih sementara jika tidak ada template
        im = Image.new("RGB", (CARD_W, CARD_H), (255, 255, 255))
        draw = ImageDraw.Draw(im)
        draw.text((100, 100), "TEMPLATE KONTRAK BELUM TERSEDIA", fill=(255,0,0), font=_load_font(60))
        draw.text((100, 180), f"Harap upload {TEMPLATE_PATH.name} ke folder assets/", fill=(255,0,0), font=_load_font(40))
    else:
        im = Image.open(TEMPLATE_PATH).convert("RGBA")
        
    # Buat background putih murni untuk blend RGB (karena multiply lebih baik di RGB)
    bg = Image.new("RGB", im.size, (255, 255, 255))
    if im.mode == "RGBA":
        bg.paste(im, mask=im.split()[3])
    else:
        bg.paste(im)
    im = bg

    W, H = im.size
    sx = W / CARD_W
    sy = H / CARD_H

    # Tulis teks
    draw = ImageDraw.Draw(im)
    font = _load_font(int(TEXT_SIZE * sy))

    # Nama
    nx = int(NAME_POS[0] * sx)
    ny = int(NAME_POS[1] * sy)
    draw.text((nx, ny), name, font=font, fill=TEXT_COLOR)

    # Jabatan
    rx = int(ROLE_POS[0] * sx)
    ry = int(ROLE_POS[1] * sy)
    draw.text((rx, ry), role_detail, font=font, fill=TEXT_COLOR)

    # Periode
    px = int(PERIOD_POS[0] * sx)
    py = int(PERIOD_POS[1] * sy)
    draw.text((px, py), period_str, font=font, fill=TEXT_COLOR)

    # Tanda Tangan
    if ttd_bytes:
        _paste_ttd_multiply(im, ttd_bytes, sx, sy)

    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
