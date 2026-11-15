"""Parser data kelulusan, transkrip, dan ijazah dari Template IPK.xlsx."""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl

from bot.settings import ROOT

log = logging.getLogger(__name__)

EXCEL_PATH = ROOT / "assets" / "Template IPK.xlsx"

MONTH_NAMES = [
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


def format_date_id(val: Any) -> str:
    """Format tanggal ke gaya bahasa Indonesia: 11 Mei 2010."""
    if isinstance(val, (datetime, date)):
        return f"{val.day} {MONTH_NAMES[val.month]} {val.year}"
    if isinstance(val, (int, float)):
        try:
            dt = datetime(1899, 12, 30) + timedelta(days=val)
            return f"{dt.day} {MONTH_NAMES[dt.month]} {dt.year}"
        except Exception:
            return str(val)
    if isinstance(val, str) and val.strip():
        val_clean = val.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(val_clean[:10], fmt)
                return f"{dt.day} {MONTH_NAMES[dt.month]} {dt.year}"
            except Exception:
                continue
        return val_clean
    return "—"


@dataclass
class CourseGrade:
    kode: str
    nama: str
    sks: int
    nilai: str
    ip: str


@dataclass
class ClubGrade:
    nama: str
    sks: int
    nilai: str
    ip: str = ""


@dataclass
class StudentGraduationData:
    nama: str
    nim: str
    ttl: str
    jurusan: str
    fakultas: str
    courses: list[CourseGrade]
    ipk: str
    predikat: str
    clubs: list[ClubGrade]
    ikk: str
    is_lulus: bool
    generasi: str = "1"


_CACHE_DATA: dict[str, StudentGraduationData] = {}
_CACHE_MTIME: float | None = None


def _load_workbook_data() -> dict[str, StudentGraduationData]:
    global _CACHE_DATA, _CACHE_MTIME
    if not EXCEL_PATH.exists():
        log.warning("File Excel tidak ditemukan: %s", EXCEL_PATH)
        return _CACHE_DATA

    try:
        current_mtime = EXCEL_PATH.stat().st_mtime
    except Exception:
        current_mtime = None

    if current_mtime is not None and _CACHE_MTIME == current_mtime and _CACHE_DATA:
        return _CACHE_DATA

    wb = None
    try:
        wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
    except PermissionError:
        # File sedang dibuka di Excel (Windows lock) -> copy ke file temp dan baca
        log.warning("File Excel terkunci oleh proses lain, mencoba membaca dari salinan sementara...")
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
                temp_path = Path(tf.name)
            shutil.copy2(EXCEL_PATH, temp_path)
            wb = openpyxl.load_workbook(str(temp_path), data_only=True)
            try:
                temp_path.unlink()
            except Exception:
                pass
        except Exception as e_copy:
            log.error("Gagal membaca salinan sementara Excel: %s", e_copy)
            return _CACHE_DATA
    except Exception as e:
        log.error("Gagal membaca Excel kelulusan: %s", e)
        return _CACHE_DATA

    if not wb or "bulk" not in wb.sheetnames:
        log.warning("Sheet 'bulk' tidak ditemukan di %s", EXCEL_PATH)
        return _CACHE_DATA

    s_bulk = wb["bulk"]
    data_map: dict[str, StudentGraduationData] = {}

    for r in range(2, s_bulk.max_row + 1):
        raw_nama = s_bulk.cell(r, 1).value
        raw_nim = s_bulk.cell(r, 2).value
        if not raw_nama or not raw_nim:
            continue

        nama = str(raw_nama).strip()
        nim = str(raw_nim).strip()
        if nim.endswith(".0"):
            nim = nim[:-2]

        ttl = format_date_id(s_bulk.cell(r, 3).value)
        jurusan = str(s_bulk.cell(r, 4).value or "").strip()
        fakultas = str(s_bulk.cell(r, 5).value or "").strip()

        # 4 Matkul Akademik
        courses: list[CourseGrade] = []
        for i, col_start in enumerate([6, 11, 16, 21]):
            kode = str(s_bulk.cell(r, col_start).value or "").strip()
            mk_name = str(s_bulk.cell(r, col_start + 1).value or "").strip()
            sks_raw = s_bulk.cell(r, col_start + 2).value
            try:
                sks = int(float(sks_raw or 0))
            except (ValueError, TypeError):
                sks = 0
            nilai = str(s_bulk.cell(r, col_start + 3).value or "").strip()
            ip = str(s_bulk.cell(r, col_start + 4).value or "").strip()

            if mk_name:
                courses.append(CourseGrade(kode=kode, nama=mk_name, sks=sks, nilai=nilai, ip=ip))

        raw_ipk = s_bulk.cell(r, 26).value
        ipk_str = str(raw_ipk if raw_ipk is not None else "0,00").strip()
        predikat = str(s_bulk.cell(r, 27).value or "-").strip()

        # 3 UKM
        clubs: list[ClubGrade] = []
        for i, col_start in enumerate([28, 32, 36]):
            ukm_name = str(s_bulk.cell(r, col_start).value or "").strip()
            sks_raw = s_bulk.cell(r, col_start + 1).value
            try:
                sks = int(float(sks_raw or 0))
            except (ValueError, TypeError):
                sks = 0
            nilai = str(s_bulk.cell(r, col_start + 2).value or "").strip()
            ip = str(s_bulk.cell(r, col_start + 3).value or "").strip()

            if ukm_name:
                clubs.append(ClubGrade(nama=ukm_name, sks=sks, nilai=nilai, ip=ip))

        raw_ikk = s_bulk.cell(r, 40).value
        ikk_str = str(raw_ikk if raw_ikk is not None else "0,00").strip()

        # Evaluasi kelulusan
        is_lulus = False
        try:
            ipk_float = float(ipk_str.replace(",", "."))
            if ipk_float > 2.00:
                is_lulus = True
        except ValueError:
            pass

        record = StudentGraduationData(
            nama=nama,
            nim=nim,
            ttl=ttl,
            jurusan=jurusan,
            fakultas=fakultas,
            courses=courses,
            ipk=ipk_str,
            predikat=predikat,
            clubs=clubs,
            ikk=ikk_str,
            is_lulus=is_lulus,
            generasi="1",
        )
        data_map[nim] = record

    _CACHE_DATA = data_map
    _CACHE_MTIME = current_mtime
    log.info("Berhasil memuat %d data shishya dari %s", len(data_map), EXCEL_PATH.name)
    return _CACHE_DATA


def get_student_by_nim(nim: str | int) -> StudentGraduationData | None:
    data = _load_workbook_data()
    clean_nim = str(nim).strip()
    if clean_nim.endswith(".0"):
        clean_nim = clean_nim[:-2]
    return data.get(clean_nim)


def get_student_by_name(name: str, exact_only: bool = False) -> StudentGraduationData | None:
    data = _load_workbook_data()
    needle = name.strip().lower()
    if not needle:
        return None

    # 1. Exact match
    for s in data.values():
        if s.nama.strip().lower() == needle:
            return s

    if exact_only:
        return None

    # 2. Substring match (hanya jika needle >= 3 karakter untuk mencegah salah sasaran)
    if len(needle) >= 3:
        for s in data.values():
            if needle in s.nama.strip().lower():
                return s

    return None


def get_all_students() -> list[StudentGraduationData]:
    return list(_load_workbook_data().values())


def get_all_graduates() -> list[StudentGraduationData]:
    return [s for s in _load_workbook_data().values() if s.is_lulus]
