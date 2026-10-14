import asyncio
import time
from datetime import datetime
import pytest

from bot.handlers.kontrak import calculate_contract_period, _get_contract_status

def test_calculate_contract_period():
    # 1. Bulan ganjil (Januari) -> Berakhir 17 Februari
    dt_jan = datetime(2026, 1, 15, 12, 0, 0)
    s_str, e_str, _ = calculate_contract_period(dt_jan.timestamp(), is_new_or_renew=True)
    assert s_str == "15 Januari 2026"
    assert e_str == "17 Februari 2026"

    # 2. Bulan genap sebelum H-7 (5 Februari) -> Berakhir 17 Februari
    dt_feb_early = datetime(2026, 2, 5, 12, 0, 0)
    s_str, e_str, _ = calculate_contract_period(dt_feb_early.timestamp(), is_new_or_renew=True)
    assert s_str == "5 Februari 2026"
    assert e_str == "17 Februari 2026"

    # 3. Bulan genap saat H-7 (10 Februari) -> Loncat ke 17 April
    dt_feb_h7 = datetime(2026, 2, 10, 12, 0, 0)
    s_str, e_str, _ = calculate_contract_period(dt_feb_h7.timestamp(), is_new_or_renew=True)
    assert s_str == "10 Februari 2026"
    assert e_str == "17 April 2026"

    # 4. Bulan genap saat ini (14 Oktober 2026, H-3 sebelum 17 Oktober) -> Loncat ke 17 Desember
    dt_oct_now = datetime(2026, 10, 14, 15, 0, 0)
    s_str, e_str, _ = calculate_contract_period(dt_oct_now.timestamp(), is_new_or_renew=True)
    assert s_str == "14 Oktober 2026"
    assert e_str == "17 Desember 2026"

    # 5. Bulan genap akhir tahun (14 Desember 2026) -> Rollover ke 17 Februari 2027
    dt_dec_now = datetime(2026, 12, 14, 15, 0, 0)
    s_str, e_str, _ = calculate_contract_period(dt_dec_now.timestamp(), is_new_or_renew=True)
    assert s_str == "14 Desember 2026"
    assert e_str == "17 Februari 2027"

    # 6. Pengecekan kalender organisasi (is_new_or_renew=False) pada 14 Oktober 2026
    # Periode aktif kalender organisasi masih 17 Oktober 2026
    _, e_cal, _ = calculate_contract_period(dt_oct_now.timestamp(), is_new_or_renew=False)
    assert e_cal == "17 Oktober 2026"

def test_contract_status_logic():
    now_ts = time.time()

    # 1. Belum punya kontrak
    st_empty = _get_contract_status({}, now_ts)
    assert st_empty["has_contract"] is False
    assert st_empty["status_icon"] == "❌"

    # 2. Kontrak masih aktif (> 7 hari lagi)
    profile_active = {
        "contract_seq_no": 5,
        "contract_end_ts": now_ts + (30 * 86400),
        "ttd_file_id": "file123",
    }
    st_active = _get_contract_status(profile_active, now_ts)
    assert st_active["has_contract"] is True
    assert st_active["is_active"] is True
    assert st_active["is_expiring"] is False
    assert st_active["is_expired"] is False
    assert st_active["status_icon"] == "✅"

    # 3. Kontrak dalam masa H-7
    profile_expiring = {
        "contract_seq_no": 5,
        "contract_end_ts": now_ts + (3 * 86400),
        "ttd_file_id": "file123",
    }
    st_expiring = _get_contract_status(profile_expiring, now_ts)
    assert st_expiring["is_active"] is False
    assert st_expiring["is_expiring"] is True
    assert st_expiring["is_expired"] is False
    assert st_expiring["status_icon"] == "⚠️"

    # 4. Kontrak sudah kadaluarsa
    profile_expired = {
        "contract_seq_no": 5,
        "contract_end_ts": now_ts - (1 * 86400),
        "ttd_file_id": "file123",
    }
    st_expired = _get_contract_status(profile_expired, now_ts)
    assert st_expired["is_active"] is False
    assert st_expired["is_expiring"] is False
    assert st_expired["is_expired"] is True
    assert st_expired["status_icon"] == "❌"
