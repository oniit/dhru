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
