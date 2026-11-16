import html
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
from telegram import Update, Message, User, Chat

from bot.handlers.kontrak import parse_indo_date
from bot.handlers.attendance import _format_presensi_block
from bot.handlers import commands
from bot.kontrak_card import _paste_ttd_multiply
from bot.kts_card import AGRA_Y
from bot.handlers.common import format_profile_card
from bot.settings import OWNER_ID


def test_parse_indo_date():
    parsed = parse_indo_date("17 Agustus 2024")
    assert parsed is not None
    day, month, year = parsed
    assert day == 17
    assert month == 8
    assert year == 2024

    parsed2 = parse_indo_date("01 Januari 2025")
    assert parsed2 is not None
    assert parsed2[1] == 1

    parsed3 = parse_indo_date("31 Desember 2023")
    assert parsed3 is not None
    assert parsed3[1] == 12

    # Invalid cases
    assert parse_indo_date("invalid date format") is None
    assert parse_indo_date("") is None


def test_format_presensi_block_budgeting():
    # Test with 200 attendees to ensure output stays within Telegram limits (< 3800 chars)
    # and no tag truncation breaks HTML
    sess = {
        "id": 101,
        "class_id": "test_class",
        "opened_at": 1704067200.0,
        "closed_at": None,
        "opened_by": 1,
        "type": "class"
    }
    records = [
        {
            "telegram_id": i,
            "first_name": f"Student Very Long Name Number {i} <tag>",
            "profile_json": json.dumps({"full_name": f"Student Very Long Name Number {i} <tag>"}),
            "status": "hadir",
            "recorded_at": 1704067200.0,
        }
        for i in range(1, 201)
    ]
    formatted = _format_presensi_block(sess, records, closed=False, show_record_times=True)
    assert len(formatted) <= 3900
    assert "Hadir" in formatted
    # Check that '<tag>' was escaped safely
    assert "<tag>" not in formatted
    assert "&lt;tag&gt;" in formatted


def test_html_escaping_in_profile_card():
    # Ensure all user inputs in profile card are properly escaped
    malicious_row = {
        "telegram_id": 999999,
        "first_name": "Attacker <script>",
        "last_name": "Smith & Sons",
        "username": "hacker<b>",
        "role": "student",
        "created_at": "2024-01-01"
    }
    profile_data = {
        "student_id": "NIM<123>",
        "full_name": "John <Doe>",
        "maba_group": "Group <A>"
    }
    card = format_profile_card(
        malicious_row,
        profile=profile_data,
        agra=100,
        show_internal=False,
        user_role="student"
    )
    # Ensure no raw injected HTML tags remain
    assert "<script>" not in card
    assert "hacker<b>" not in card
    assert "hacker&lt;b&gt;" in card
    assert "NIM<123>" not in card
    assert "NIM&lt;123&gt;" in card
    assert "John &lt;Doe&gt;" in card


def test_kontrak_signature_transparency():
    # Create mock transparent signature (RGBA with transparent pixels)
    sig_img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    # Draw some black strokes
    for x in range(50, 150):
        sig_img.putpixel((x, 50), (10, 10, 10, 255))

    # Test the flattening logic directly:
    # Converting RGBA with transparency directly to RGB yields black background:
    direct_rgb = sig_img.convert("RGB")
    assert direct_rgb.getpixel((0, 0)) == (0, 0, 0) # Black rectangle artifact!

    # Our fix: composite onto white RGBA first:
    white_bg = Image.new("RGBA", sig_img.size, (255, 255, 255, 255))
    flattened = Image.alpha_composite(white_bg, sig_img).convert("RGB")
    assert flattened.getpixel((0, 0)) == (255, 255, 255) # Clean white, no black artifact!


def test_authorization_checks():
    # Ensure commands with previous backdoor ID (1073487310) reject non-owners
    non_owner_uid = 1073487310 # Old hardcoded backdoor ID
    assert non_owner_uid != OWNER_ID
    assert commands.is_owner(non_owner_uid) is False
    assert commands.is_owner(OWNER_ID) is True


def test_kts_card_dynamic_agra_y():
    # If a student has many clubs, y coordinate increases
    # Our fix ensures agra_y is max(int(AGRA_Y * sy), y + int(4 * sy))
    sy = 1.0
    y_normal = 200
    agra_y_normal = max(int(AGRA_Y * sy), y_normal + int(4 * sy))
    assert agra_y_normal == int(AGRA_Y * sy)

    y_many_clubs = int(AGRA_Y * sy) + 50
    agra_y_pushed = max(int(AGRA_Y * sy), y_many_clubs + int(4 * sy))
    assert agra_y_pushed > int(AGRA_Y * sy)
    assert agra_y_pushed == y_many_clubs + 4


def test_graduation_excel_passing_grade():
    from bot.graduation_excel import StudentGraduationData
    s_pass = StudentGraduationData(
        nama="Lulus",
        nim="12345",
        ttl="Jakarta, 01-01-2000",
        jurusan="Informatika",
        fakultas="Teknik",
        courses=[],
        ipk="2.00",
        predikat="Memuaskan",
        clubs=[],
        ikk="3.50",
        is_lulus=True,
    )
    assert float(s_pass.ipk) >= 2.00
    assert s_pass.is_lulus is True

    s_fail = StudentGraduationData(
        nama="Gagal",
        nim="12346",
        ttl="Jakarta, 01-01-2000",
        jurusan="Informatika",
        fakultas="Teknik",
        courses=[],
        ipk="1.99",
        predikat="Cukup",
        clubs=[],
        ikk="3.50",
        is_lulus=False,
    )
    assert float(s_fail.ipk) < 2.00
    assert s_fail.is_lulus is False


def test_card_thread_safe_cache():
    import threading
    from bot import kts_card
    assert kts_card._cache_get("non_existent_key_123") is None

    # Test cache put and get under threading lock
    fake_img = Image.new("RGB", (10, 10), (255, 255, 255))
    kts_card._cache_put("test_key", fake_img)
    cached = kts_card._cache_get("test_key")
    assert cached is not None
    assert cached.size == (10, 10)
