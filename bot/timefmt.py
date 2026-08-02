"""Format waktu untuk tampilan (WIB)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jakarta")


def format_local_time(ts: float | None) -> str:
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(float(ts), tz=TZ)
    return dt.strftime("%d/%m/%Y %H:%M WIB")

def format_time_only(ts: float | None) -> str:
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(float(ts), tz=TZ)
    return dt.strftime("%H:%M:%S WIB")

def get_today_wib() -> datetime.date:
    return datetime.now(TZ).date()

def days_until_next_birthday(birth_date_str: str) -> int:
    """Returns days until next birthday from today (WIB). Returns 99999 if invalid."""
    raw = (birth_date_str or "").strip()
    if len(raw) != 6 or not raw.isdigit():
        return 99999
    
    dd = int(raw[:2])
    mm = int(raw[2:4])
    
    today = get_today_wib()
    
    def _get_bday(year: int, m: int, d: int) -> datetime.date:
        try:
            return datetime(year, m, d).date()
        except ValueError:
            # Handle leaplings (Feb 29) on non-leap years
            if m == 2 and d == 29:
                return datetime(year, 3, 1).date()
            raise
            
    try:
        bday_this_year = _get_bday(today.year, mm, dd)
        if bday_this_year < today:
            bday_next_year = _get_bday(today.year + 1, mm, dd)
            return (bday_next_year - today).days
        else:
            return (bday_this_year - today).days
    except ValueError:
        return 99999
