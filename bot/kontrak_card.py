"""Render Kontrak (PNG) dari template + TTD."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageChops

from bot.settings import ROOT

log = logging.getLogger(__name__)

TEMPLATE_PATH = ROOT / "assets" / "kontrak.png"
MUKTA_FONT_PATH = ROOT / "assets" / "Mukta/Mukta-Regular.ttf"

# Koordinat perkiraan untuk template A4/Dokumen (misal 1240 x 1754 pixel)
CARD_W, CARD_H = 1240, 1754
TEXT_COLOR = "#333132"

# Posisi teks:
# (x, y) untuk Nama, Jabatan, Masa Akhir Kontrak
# Ubah angka X dan Y di bawah ini untuk menggeser posisinya!
NAME_POS = (342, 590)
ROLE_POS = (342, 622)
USERNAME_POS = (342, 654)
END_DATE_POS = (666, 1185)

TEXT_SIZE = 25

# Posisi tanggal mulai (di atas TTD)
START_DATE_POS = (895, 1342)

TEXT_SIZE = 25

# Posisi kotak TTD di bagian bawah dokumen
TTD_SLOT = (820, 1380, 200, 150) # x, y, width, height

# Posisi Nama (ditulis ulang di bawah TTD)
# Koordinat X (910) adalah titik tengah dari kotak TTD (810 + 200/2)
NAME_BOTTOM_POS = (920, 1510)

# Ukuran font khusus untuk nama di bawah TTD (misalnya lebih besar sedikit)
TEXT_SIZE_BOTTOM = 28


def _load_mukta_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(MUKTA_FONT_PATH), size=size)
    except OSError:
        return _load_font(size, is_bold=False)

def _load_font(size: int, is_bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    asset_font_name = "ARIALBD.TTF" if is_bold else "ARIAL.TTF"
    asset_font_path = ROOT / "assets" / asset_font_name
    
    try:
        return ImageFont.truetype(str(asset_font_path), size=size)
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
    username: str,
    start_date_str: str,
    end_date_str: str,
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
    font_regular = _load_font(int(TEXT_SIZE * sy), is_bold=False)
    font_bold = _load_font(int(TEXT_SIZE * sy), is_bold=True)
    font_mukta = _load_mukta_font(int(TEXT_SIZE_BOTTOM * sy))

    # Nama (Bold)
    nx = int(NAME_POS[0] * sx)
    ny = int(NAME_POS[1] * sy)
    draw.text((nx, ny), name, font=font_bold, fill=TEXT_COLOR)

    # Nama (Di bawah TTD, Mukta, Kapital Semua, Tengah, Truncate)
    display_name = name.upper()
    max_w = int(400 * sx)  # Batas lebar maksimal teks diperlebar jadi 450 pixel
    if draw.textlength(display_name, font=font_mukta) > max_w:
        while len(display_name) > 0 and draw.textlength(display_name + "...", font=font_mukta) > max_w:
            display_name = display_name[:-1]
        display_name += "..."

    nb_x = int(NAME_BOTTOM_POS[0] * sx)
    nb_y = int(NAME_BOTTOM_POS[1] * sy)
    # anchor="mt" berarti posisi nb_x adalah middle (tengah), nb_y adalah top (atas)
    draw.text((nb_x, nb_y), display_name, font=font_mukta, fill=TEXT_COLOR, anchor="mt")

    # Jabatan (Bold)
    rx = int(ROLE_POS[0] * sx)
    ry = int(ROLE_POS[1] * sy)
    draw.text((rx, ry), role_detail, font=font_bold, fill=TEXT_COLOR)

    # Username (Bold)
    ux = int(USERNAME_POS[0] * sx)
    uy = int(USERNAME_POS[1] * sy)
    draw.text((ux, uy), username, font=font_bold, fill=TEXT_COLOR)

    # Masa Akhir Kontrak (Bold)
    px = int(END_DATE_POS[0] * sx)
    py = int(END_DATE_POS[1] * sy)
    draw.text((px, py), end_date_str, font=font_bold, fill=TEXT_COLOR)

    # Tanggal Mulai Kontrak (Regular)
    sx_start = int(START_DATE_POS[0] * sx)
    sy_start = int(START_DATE_POS[1] * sy)
    draw.text((sx_start, sy_start), start_date_str, font=font_regular, fill=TEXT_COLOR)

    # Tanda Tangan
    if ttd_bytes:
        _paste_ttd_multiply(im, ttd_bytes, sx, sy)

    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
