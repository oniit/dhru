"""Parser data kelulusan, transkrip, dan ijazah dari Template IPK.xlsx dan arsip JSON/Turso."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl

from bot.settings import GENERATION_CODE, ROOT

log = logging.getLogger(__name__)

EXCEL_PATH = ROOT / "assets" / "Template IPK.xlsx"
JSON_ARCHIVE_PATH = ROOT / "data" / "graduation_records.json"

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

    def to_dict(self) -> dict:
        return {
            "kode": self.kode,
            "nama": self.nama,
            "sks": self.sks,
            "nilai": self.nilai,
            "ip": self.ip,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CourseGrade:
        return cls(
            kode=str(d.get("kode", "")),
            nama=str(d.get("nama", "")),
            sks=int(d.get("sks", 0)),
            nilai=str(d.get("nilai", "")),
            ip=str(d.get("ip", "")),
        )


@dataclass
class ClubGrade:
    nama: str
    sks: int
    nilai: str
    ip: str = ""

    def to_dict(self) -> dict:
        return {
            "nama": self.nama,
            "sks": self.sks,
            "nilai": self.nilai,
            "ip": self.ip,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ClubGrade:
        return cls(
            nama=str(d.get("nama", "")),
            sks=int(d.get("sks", 0)),
            nilai=str(d.get("nilai", "")),
            ip=str(d.get("ip", "")),
        )


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

    def to_dict(self) -> dict:
        return {
            "nama": self.nama,
            "nim": self.nim,
            "ttl": self.ttl,
            "jurusan": self.jurusan,
            "fakultas": self.fakultas,
            "courses": [c.to_dict() for c in self.courses],
            "ipk": self.ipk,
            "predikat": self.predikat,
            "clubs": [cl.to_dict() for cl in self.clubs],
            "ikk": self.ikk,
            "is_lulus": self.is_lulus,
            "generasi": self.generasi,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StudentGraduationData:
        courses = [CourseGrade.from_dict(c) for c in d.get("courses", [])]
        clubs = [ClubGrade.from_dict(cl) for cl in d.get("clubs", [])]
        return cls(
            nama=str(d.get("nama", "")),
            nim=str(d.get("nim", "")),
            ttl=str(d.get("ttl", "")),
            jurusan=str(d.get("jurusan", "")),
            fakultas=str(d.get("fakultas", "")),
            courses=courses,
            ipk=str(d.get("ipk", "0,00")),
            predikat=str(d.get("predikat", "-")),
            clubs=clubs,
            ikk=str(d.get("ikk", "0,00")),
            is_lulus=bool(d.get("is_lulus", False)),
            generasi=str(d.get("generasi", "1")),
        )


# In-memory unified cache for fast lookup (zero Turso reads)
_ARCHIVE_DATA: dict[str, StudentGraduationData] = {}
_ARCHIVE_MTIME: float | None = None
_EXCEL_MTIME: float | None = None


def load_archive_json() -> dict[str, StudentGraduationData]:
    """Muat seluruh data kelulusan dari arsip JSON lokal."""
    global _ARCHIVE_DATA, _ARCHIVE_MTIME
    if not JSON_ARCHIVE_PATH.exists():
        return _ARCHIVE_DATA

    try:
        current_mtime = JSON_ARCHIVE_PATH.stat().st_mtime
        if _ARCHIVE_MTIME == current_mtime and _ARCHIVE_DATA:
            return _ARCHIVE_DATA

        with open(JSON_ARCHIVE_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        data_map: dict[str, StudentGraduationData] = {}
        for nim, item in raw_data.items():
            st = StudentGraduationData.from_dict(item)
            data_map[st.nim] = st
            data_map[st.nim.lstrip("0")] = st
            if len(st.nim) == 10 and st.nim.isdigit():
                data_map[st.nim.zfill(11)] = st

        _ARCHIVE_DATA = data_map
        _ARCHIVE_MTIME = current_mtime
    except Exception as e:
        log.error("Gagal membaca file arsip kelulusan %s: %s", JSON_ARCHIVE_PATH, e)

    return _ARCHIVE_DATA


def save_archive_json(data: dict[str, StudentGraduationData]) -> None:
    """Simpan data kelulusan ke file JSON secara atomik."""
    global _ARCHIVE_DATA, _ARCHIVE_MTIME
    try:
        JSON_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        unique_records = {}
        for st in data.values():
            unique_records[st.nim] = st.to_dict()

        with tempfile.NamedTemporaryFile("w", dir=str(JSON_ARCHIVE_PATH.parent), delete=False, encoding="utf-8") as tf:
            json.dump(unique_records, tf, ensure_ascii=False, indent=2)
            temp_name = tf.name

        Path(temp_name).replace(JSON_ARCHIVE_PATH)
        _ARCHIVE_MTIME = JSON_ARCHIVE_PATH.stat().st_mtime
        log.info("Arsip kelulusan berhasil diperbarui: %d mahasiswa tersimpan di %s", len(unique_records), JSON_ARCHIVE_PATH.name)
    except Exception as e:
        log.error("Gagal menyimpan arsip kelulusan JSON: %s", e)


def _sync_excel_into_archive(force: bool = False) -> bool:
    """Sinkronkan data dari Template IPK.xlsx aktif ke dalam arsip JSON (auto-merge)."""
    global _EXCEL_MTIME, _ARCHIVE_DATA
    if not EXCEL_PATH.exists():
        return False

    try:
        current_mtime = EXCEL_PATH.stat().st_mtime
    except Exception:
        current_mtime = None

    archive_mtime = JSON_ARCHIVE_PATH.stat().st_mtime if JSON_ARCHIVE_PATH.exists() else 0
    if not force and current_mtime is not None and (current_mtime <= archive_mtime or _EXCEL_MTIME == current_mtime) and _ARCHIVE_DATA:
        _EXCEL_MTIME = current_mtime
        return False

    wb = None
    try:
        wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
    except PermissionError:
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
            return False
    except Exception as e:
        log.error("Gagal membaca Excel kelulusan: %s", e)
        return False

    if not wb or "bulk" not in wb.sheetnames:
        log.warning("Sheet 'bulk' tidak ditemukan di %s", EXCEL_PATH)
        return False

    s_bulk = wb["bulk"]
    gen_val = GENERATION_CODE.lstrip("0") or GENERATION_CODE or "1"
    parsed_any = False

    for r in range(2, s_bulk.max_row + 1):
        raw_nama = s_bulk.cell(r, 1).value
        raw_nim = s_bulk.cell(r, 2).value
        if not raw_nama or not raw_nim:
            continue

        nama = str(raw_nama).strip()
        nim = str(raw_nim).strip()
        if nim.endswith(".0"):
            nim = nim[:-2]
        if len(nim) == 10 and nim.isdigit():
            nim = nim.zfill(11)

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
            generasi=str(gen_val),
        )

        _ARCHIVE_DATA[nim] = record
        _ARCHIVE_DATA[nim.lstrip("0")] = record
        if len(nim) == 10 and nim.isdigit():
            _ARCHIVE_DATA[nim.zfill(11)] = record
        parsed_any = True

    _EXCEL_MTIME = current_mtime
    if parsed_any:
        save_archive_json(_ARCHIVE_DATA)
        log.info("Sinkronisasi Excel ke JSON berhasil. Total data arsip: %d", len(_ARCHIVE_DATA))
        return True

    return False


def _load_workbook_data() -> dict[str, StudentGraduationData]:
    """Muat data: Prioritas dari arsip JSON terlebih dahulu, lalu sinkronkan dari Excel jika ada pembaruan."""
    global _ARCHIVE_DATA
    load_archive_json()
    _sync_excel_into_archive()
    return _ARCHIVE_DATA


def get_student_by_nim(nim: str | int) -> StudentGraduationData | None:
    data = _load_workbook_data()
    clean_nim = str(nim).strip()
    if clean_nim.endswith(".0"):
        clean_nim = clean_nim[:-2]

    # Prioritas 1: Baca langsung dari in-memory cache (JSON)
    if clean_nim in data:
        return data[clean_nim]
    if clean_nim.zfill(11) in data:
        return data[clean_nim.zfill(11)]
    if clean_nim.lstrip("0") in data:
        return data[clean_nim.lstrip("0")]

    # Fallback: Coba sinkronisasi ulang Excel jika ada file baru masuk
    if _sync_excel_into_archive(force=True):
        data = _ARCHIVE_DATA
        if clean_nim in data:
            return data[clean_nim]
        if clean_nim.zfill(11) in data:
            return data[clean_nim.zfill(11)]
        if clean_nim.lstrip("0") in data:
            return data[clean_nim.lstrip("0")]

    return None


def get_student_by_name(name: str, exact_only: bool = False) -> StudentGraduationData | None:
    data = _load_workbook_data()
    needle = name.strip().lower()
    if not needle:
        return None

    # Prioritas 1: Exact match dari in-memory cache (JSON)
    for s in data.values():
        if s.nama.strip().lower() == needle:
            return s

    if not exact_only and len(needle) >= 3:
        for s in data.values():
            if needle in s.nama.strip().lower():
                return s

    # Fallback: Coba sinkronisasi ulang Excel jika ada file baru masuk
    if _sync_excel_into_archive(force=True):
        data = _ARCHIVE_DATA
        for s in data.values():
            if s.nama.strip().lower() == needle:
                return s
        if not exact_only and len(needle) >= 3:
            for s in data.values():
                if needle in s.nama.strip().lower():
                    return s

    return None


def get_all_students(generasi: str | None = None) -> list[StudentGraduationData]:
    data = _load_workbook_data()
    seen = set()
    res = []
    for s in data.values():
        if s.nim not in seen:
            seen.add(s.nim)
            if generasi is None or str(s.generasi) == str(generasi):
                res.append(s)
    return res


def get_all_graduates(generasi: str | None = None) -> list[StudentGraduationData]:
    data = _load_workbook_data()
    seen = set()
    res = []
    for s in data.values():
        if s.nim not in seen and s.is_lulus:
            seen.add(s.nim)
            if generasi is None or str(s.generasi) == str(generasi):
                res.append(s)
    return res


async def mirror_archive_to_turso(conn, db, records: list[StudentGraduationData] | None = None) -> int:
    """Mirror data kelulusan dari arsip JSON ke database Turso."""
    if not conn or not db or not hasattr(db, "upsert_graduation_records"):
        return 0

    if not records:
        all_students = get_all_students()
        records = all_students

    dict_list = [st.to_dict() for st in records]
    try:
        count = await db.upsert_graduation_records(conn, dict_list)
        log.info("Mirroring kelulusan ke Turso berhasil: %d mahasiswa tercatat", count)
        return count
    except Exception as e:
        log.warning("Gagal me-mirror kelulusan ke Turso: %s", e)
        return 0


async def restore_archive_from_turso_if_empty(conn, db) -> int:
    """Jika file JSON kosong tapi Turso DB punya data, restore JSON dari Turso."""
    if JSON_ARCHIVE_PATH.exists() and JSON_ARCHIVE_PATH.stat().st_size > 10:
        return 0

    if not conn or not db or not hasattr(db, "get_all_graduation_records_from_db"):
        return 0

    try:
        records = await db.get_all_graduation_records_from_db(conn)
        if records:
            data_map: dict[str, StudentGraduationData] = {}
            for r in records:
                st = StudentGraduationData.from_dict(r)
                data_map[st.nim] = st
                data_map[st.nim.lstrip("0")] = st
                if len(st.nim) == 10 and st.nim.isdigit():
                    data_map[st.nim.zfill(11)] = st
            save_archive_json(data_map)
            log.info("Berhasil me-restore %d record kelulusan dari Turso ke JSON", len(records))
            return len(records)
    except Exception as e:
        log.warning("Gagal restore arsip dari Turso: %s", e)
    return 0
