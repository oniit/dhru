"""Handler untuk fitur /transkrip, /ijazah, dan /export_kelulusan."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import zipfile
from io import BytesIO
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import ROLE_ADMIN, ROLE_OWNER, ROLE_PUBLIC
from bot.graduation_excel import (
    StudentGraduationData,
    get_all_graduates,
    get_all_students,
    get_student_by_name,
    get_student_by_nim,
    mirror_archive_to_turso,
)
from bot.ijazah_card import get_degree_title, render_ijazah_png_bytes
from bot.settings import GENERATION_CODE, OWNER_ID, ROOT, is_owner
from bot.transkrip_card import render_transkrip_png_bytes

from .common import profile_from_row, rate_limit_check, user_row

log = logging.getLogger(__name__)


def _get_output_dir(gen_str: str | None = None) -> Path:
    g = (gen_str or GENERATION_CODE).lstrip("0") or (gen_str or GENERATION_CODE) or "1"
    return ROOT / "output" / f"kelulusan_gen{g}"


def _get_zip_path(gen_str: str | None = None) -> Path:
    g = (gen_str or GENERATION_CODE).lstrip("0") or (gen_str or GENERATION_CODE) or "1"
    return ROOT / "output" / f"kelulusan_gen{g}.zip"


OUTPUT_DIR = _get_output_dir()


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _private_only_reply(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


def _is_owner(row: dict | None, uid: int) -> bool:
    if is_owner(uid):
        return True
    if not row:
        return False
    return row.get("role") == ROLE_OWNER


def _is_admin_or_owner(row: dict | None, uid: int) -> bool:
    if _is_owner(row, uid):
        return True
    if not row:
        return False
    return row.get("role") == ROLE_ADMIN


async def _download_telegram_photo(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes | None:
    try:
        tg_file = await context.bot.get_file(file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        log.warning("Unduh foto kelulusan gagal file_id=%s", file_id[:20], exc_info=True)
        return None


async def _get_photo_bytes_for_student(
    context: ContextTypes.DEFAULT_TYPE,
    conn,
    db,
    student: StudentGraduationData,
    requester_uid: int,
    requester_profile: dict,
    is_target_lookup: bool,
) -> bytes | None:
    """Ambil foto pasfoto yang tepat untuk mahasiswa yang dituju.
    
    Jika admin melihat mahasiswa lain, cari foto mahasiswa tersebut di DB berdasarkan NIM.
    Jangan pernah menempelkan foto admin ke dokumen mahasiswa lain!
    """
    if not is_target_lookup:
        # Pengecekan untuk diri sendiri
        fid = (requester_profile.get("photo_file_id") or "").strip()
        if fid:
            photo = await _download_telegram_photo(context, fid)
            if photo:
                return photo

        # Fallback: coba avatar profil Telegram sendiri
        try:
            user_photos = await context.bot.get_user_profile_photos(requester_uid, limit=1)
            if user_photos.total_count > 0 and user_photos.photos:
                largest = user_photos.photos[0][-1]
                return await _download_telegram_photo(context, largest.file_id)
        except Exception:
            pass
        return None

    # Target lookup oleh admin: cari di database user dengan NIM ini (dukung 11-digit & 10-digit)
    if conn:
        try:
            candidates = tuple({student.nim, student.nim.zfill(11), student.nim.lstrip("0")})
            ph = ",".join("?" for _ in candidates)
            cur = await conn.execute(
                f"SELECT telegram_id, profile_json FROM users WHERE json_extract(profile_json, '$.student_id') IN ({ph})",
                candidates,
            )
            row = await cur.fetchone()
            if row:
                p = json.loads(row["profile_json"] or "{}")
                fid = (p.get("photo_file_id") or "").strip()
                if fid:
                    photo = await _download_telegram_photo(context, fid)
                    if photo:
                        return photo
                
                # Fallback ke foto profil Telegram shishya bersangkutan jika belum set pasfoto KTS
                target_uid = row["telegram_id"]
                if target_uid:
                    try:
                        user_photos = await context.bot.get_user_profile_photos(int(target_uid), limit=1)
                        if user_photos.total_count > 0 and user_photos.photos:
                            largest = user_photos.photos[0][-1]
                            return await _download_telegram_photo(context, largest.file_id)
                    except Exception:
                        pass
        except Exception as e:
            log.warning("Gagal mencari foto shishya NIM %s di DB: %s", student.nim, e)

    return None


def _find_student(
    target_str: str, profile: dict, row: dict | None, is_admin: bool
) -> StudentGraduationData | None:
    """Cari mahasiswa secara ketat dan aman.
    
    - Admin dengan argumen: mencari via NIM atau nama (exact atau substring >= 3 chars).
    - Mahasiswa mandiri: HANYA via student_id (NIM) atau exact full_name resmi di profile_json.
      TIDAK PERNAH mencocokkan first_name Telegram mentah demi mencegah pencurian identitas (IDOR).
    """
    if target_str:
        if not is_admin:
            return None
        # 1. Coba NIM
        st = get_student_by_nim(target_str)
        if st:
            return st
        # 2. Coba Nama
        st = get_student_by_name(target_str, exact_only=False)
        if st:
            return st
        return None

    # Pencarian mandiri (Self-Service)
    # Wajib menggunakan NIM resmi yang tersimpan di profil
    nim = (profile.get("student_id") or "").strip()
    if nim:
        st = get_student_by_nim(nim)
        if st:
            return st

    return None


async def cmd_transkrip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perintah /transkrip [nim/nama] — Menampilkan Transkrip Nilai Akademik."""
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text(
            "🔒 Perintah <code>/transkrip</code> hanya dapat digunakan di chat privat dengan bot demi privasi nilai Anda."
        )
        return

    uid = update.effective_user.id
    if not rate_limit_check(uid, "transkrip", 4):
        await update.message.reply_text("Tunggu sebentar sebelum meminta dokumen lagi.")
        return

    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start terlebih dahulu.")
        return

    role = row.get("role", ROLE_PUBLIC)
    is_admin = _is_admin_or_owner(row, uid)

    if role == ROLE_PUBLIC and not is_admin:
        await update.message.reply_text(
            "⚠️ Anda belum terdaftar sebagai Shishya. Selesaikan pendaftaran profil terlebih dahulu."
        )
        return

    profile = profile_from_row(row)
    args = context.args or []
    target_query = " ".join(args).strip() if args else ""

    if target_query and not is_admin:
        await update.message.reply_text("Hanya admin yang dapat melihat transkrip shishya lain.")
        return

    student = _find_student(target_query, profile, row, is_admin=is_admin)

    if not student:
        if is_admin and not target_query:
            await update.message.reply_text(
                "📋 <b>Cetak Transkrip Nilai (Admin Mode)</b>\n\n"
                "Format: <code>/transkrip &lt;NIM atau Nama&gt;</code>\n"
                "Contoh: <code>/transkrip 2004010093</code>\n"
                "Atau: <code>/transkrip Aluna</code>"
            )
            return

        await update.message.reply_text(
            "❌ Data transkrip akademik Anda belum tercatat di sistem Gen 1.\n\n"
            "Pastikan NIM pada profil Anda sudah sesuai atau hubungi Biro Akademik jika Anda merupakan shishya aktif."
        )
        return

    # Siapkan foto mahasiswa yang dituju
    is_target_lookup = bool(target_query and is_admin)
    photo_bytes = await _get_photo_bytes_for_student(
        context, conn, db, student, uid, profile, is_target_lookup=is_target_lookup
    )

    status_msg = await update.message.reply_text("⏳ Sedang memproses Transkrip Nilai...")

    try:
        png_bytes = await asyncio.to_thread(
            render_transkrip_png_bytes,
            student=student,
            photo_bytes=photo_bytes,
        )
    except Exception as e:
        log.exception("Gagal me-render transkrip NIM %s: %s", student.nim, e)
        await status_msg.edit_text("❌ Terjadi kesalahan saat membuat Transkrip Nilai.")
        return

    nama_esc = html.escape(student.nama)
    jurusan_esc = html.escape(student.jurusan)
    predikat_esc = html.escape(student.predikat)

    cap = (
        f"📄 <b>Transkrip Nilai Akademik</b>\n"
        f"<b>Nama:</b> {nama_esc}\n"
        f"<b>NIM:</b> <code>{student.nim}</code>\n"
        f"<b>Jurusan:</b> {jurusan_esc}\n"
        f"<b>IPK:</b> <b>{student.ipk}</b> | <b>Predikat:</b> {predikat_esc}"
    )

    await update.message.reply_photo(
        photo=BytesIO(png_bytes),
        filename=f"Transkrip_{student.nim}.png",
        caption=cap,
        read_timeout=60,
        write_timeout=60,
    )
    try:
        await status_msg.delete()
    except Exception:
        pass


async def cmd_ijazah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perintah /ijazah [nim/nama] — Menampilkan Ijazah Kelulusan Resmi."""
    if not update.effective_user or not update.message:
        return
    if not _private_only_reply(update):
        await update.message.reply_text(
            "🔒 Perintah <code>/ijazah</code> hanya dapat digunakan di chat privat dengan bot demi privasi Anda.",
            parse_mode="HTML"
        )
        return

    uid = update.effective_user.id
    if not rate_limit_check(uid, "ijazah", 4):
        await update.message.reply_text("Tunggu sebentar sebelum meminta dokumen lagi.")
        return

    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)
    if not row:
        await update.message.reply_text("Ketik /start terlebih dahulu.")
        return

    role = row.get("role", ROLE_PUBLIC)
    is_admin = _is_admin_or_owner(row, uid)

    if role == ROLE_PUBLIC and not is_admin:
        await update.message.reply_text(
            "⚠️ Anda belum terdaftar sebagai Shishya. Selesaikan pendaftaran profil terlebih dahulu."
        )
        return

    profile = profile_from_row(row)
    args = context.args or []
    target_query = " ".join(args).strip() if args else ""

    if target_query and not is_admin:
        await update.message.reply_text("Hanya admin yang dapat melihat ijazah shishya lain.")
        return

    student = _find_student(target_query, profile, row, is_admin=is_admin)

    if not student:
        if is_admin and not target_query:
            await update.message.reply_text(
                "🎓 <b>Cetak Ijazah Kelulusan (Admin Mode)</b>\n\n"
                "Format: <code>/ijazah &lt;NIM atau Nama&gt;</code>\n"
                "Contoh: <code>/ijazah 2004010093</code>\n"
                "Atau: <code>/ijazah Aluna</code>"
            )
            return

        await update.message.reply_text(
            "❌ Data akademik Anda belum tercatat di daftar kelulusan Gen 1.\n\n"
            "Hubungi Biro Akademik untuk konfirmasi status pendaftaran kelulusan."
        )
        return

    if not student.is_lulus:
        await update.message.reply_text(
            f"⚠️ <b>Belum Memenuhi Syarat Kelulusan</b>\n\n"
            f"Nama: <b>{html.escape(student.nama)}</b> (NIM: <code>{student.nim}</code>)\n"
            f"IPK: {student.ipk}\n\n"
            f"Berdasarkan kriteria kelulusan Gen 1, syarat kelulusan adalah memiliki IPK minimal di atas <b>2.00</b>.\n"
            f"Silakan hubungi Dosen Pembimbing atau Biro Akademik untuk program remedial/perbaikan nilai."
        )
        return

    # Siapkan foto mahasiswa yang dituju
    is_target_lookup = bool(target_query and is_admin)
    photo_bytes = await _get_photo_bytes_for_student(
        context, conn, db, student, uid, profile, is_target_lookup=is_target_lookup
    )

    status_msg = await update.message.reply_text("⏳ Sedang memproses Ijazah Kelulusan Resmi...")

    try:
        png_bytes = await asyncio.to_thread(
            render_ijazah_png_bytes,
            student=student,
            photo_bytes=photo_bytes,
        )
    except Exception as e:
        log.exception("Gagal me-render ijazah NIM %s: %s", student.nim, e)
        await status_msg.edit_text("❌ Terjadi kesalahan saat membuat Ijazah.")
        return

    nama_esc = html.escape(student.nama)
    jurusan_esc = html.escape(student.jurusan)
    fakultas_esc = html.escape(student.fakultas)
    degree_esc = html.escape(get_degree_title(student.fakultas, student.jurusan))
    predikat_esc = html.escape(student.predikat if student.predikat and student.predikat != "-" else "LULUS")

    cap = (
        f"🎓 <b>Ijazah Kelulusan Resmi</b>\n"
        f"<b>Institut Dhruva Ekāgra</b>\n\n"
        f"Selamat kepada <b>{nama_esc}</b> (NIM: <code>{student.nim}</code>)\n"
        f"<b>Jurusan:</b> {jurusan_esc} - {fakultas_esc}\n"
        f"<b>Gelar:</b> {degree_esc}\n"
        f"<b>Predikat:</b> {predikat_esc}"
    )

    await update.message.reply_photo(
        photo=BytesIO(png_bytes),
        filename=f"Ijazah_{student.nim}.png",
        caption=cap,
        read_timeout=60,
        write_timeout=60,
    )
    try:
        await status_msg.delete()
    except Exception:
        pass


async def _fetch_photos_for_graduates(
    context: ContextTypes.DEFAULT_TYPE,
    conn,
    graduates: list[StudentGraduationData],
) -> dict[str, bytes | None]:
    """Mengambil pasfoto/avatar mahasiswa kelulusan secara efisien & paralel.
    
    Menggunakan index idx_users_student_id pada Turso dengan kueri WHERE student_id IN (...)
    sehingga tetap hemat kuota pembacaan baris (read quota).
    """
    if not graduates or not conn:
        return {}

    candidate_nims = set()
    for g in graduates:
        if g.nim:
            c = g.nim.strip()
            candidate_nims.add(c)
            candidate_nims.add(c.zfill(11))
            candidate_nims.add(c.lstrip("0"))

    if not candidate_nims:
        return {}

    placeholders = ",".join("?" for _ in candidate_nims)
    sql = (
        f"SELECT telegram_id, profile_json "
        f"FROM users "
        f"WHERE json_extract(profile_json, '$.student_id') IN ({placeholders})"
    )

    student_map: dict[str, dict] = {}
    try:
        cur = await conn.execute(sql, tuple(candidate_nims))
        rows = await cur.fetchall()
        for r in rows:
            p = json.loads(r["profile_json"] or "{}")
            sid = str(p.get("student_id") or "").strip()
            fid = (p.get("photo_file_id") or "").strip()
            if sid:
                entry = {
                    "telegram_id": r["telegram_id"],
                    "photo_file_id": fid,
                }
                # Petakan ke berbagai variasi format NIM
                for variant in (sid, sid.lstrip("0"), sid.zfill(11)):
                    if variant not in student_map or (not student_map[variant]["photo_file_id"] and fid):
                        student_map[variant] = entry
    except Exception as e:
        log.warning("Gagal query data foto kelulusan dari DB: %s", e)
        return {}

    sem = asyncio.Semaphore(5)
    photos_by_nim: dict[str, bytes | None] = {}

    async def _fetch_one(st: StudentGraduationData):
        nim = st.nim
        info = student_map.get(nim) or student_map.get(nim.zfill(11)) or student_map.get(nim.lstrip("0"))
        if not info:
            return

        async with sem:
            # 1. Prioritas: foto pasfoto resmi KTS
            fid = info["photo_file_id"]
            if fid:
                data = await _download_telegram_photo(context, fid)
                if data:
                    photos_by_nim[nim] = data
                    return

            # 2. Fallback: avatar profil Telegram
            tid = info.get("telegram_id")
            if tid:
                try:
                    user_photos = await context.bot.get_user_profile_photos(int(tid), limit=1)
                    if user_photos.total_count > 0 and user_photos.photos:
                        largest = user_photos.photos[0][-1]
                        data = await _download_telegram_photo(context, largest.file_id)
                        if data:
                            photos_by_nim[nim] = data
                except Exception:
                    pass

    await asyncio.gather(*[_fetch_one(g) for g in graduates], return_exceptions=True)
    return photos_by_nim


def _sync_export_documents(
    graduates: list[StudentGraduationData],
    output_dir: Path,
    photos_map: dict[str, bytes | None] | None = None,
    gen_val: str = "1",
) -> tuple[int, list[Path]]:
    """Fungsi ekspor batch grafis murni CPU-bound yang dijalankan di thread terpisah."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files: list[Path] = []
    success_count = 0

    # 1. Tulis arsip data JSON angkatan ini langsung ke dalam output_dir
    json_export_name = f"graduation_records_gen{gen_val}.json"
    json_export_path = output_dir / json_export_name
    try:
        gen_data = {
            st.nim: {
                "nama": st.nama,
                "nim": st.nim,
                "ttl": st.ttl,
                "jurusan": st.jurusan,
                "fakultas": st.fakultas,
                "courses": [{"kode": c.kode, "nama": c.nama, "sks": c.sks, "nilai": c.nilai, "ip": c.ip} for c in st.courses],
                "ipk": st.ipk,
                "predikat": st.predikat,
                "clubs": [{"nama": cl.nama, "sks": cl.sks, "nilai": cl.nilai, "ip": cl.ip} for cl in st.clubs],
                "ikk": st.ikk,
                "is_lulus": st.is_lulus,
                "generasi": st.generasi,
            }
            for st in graduates
        }
        with open(json_export_path, "w", encoding="utf-8") as jf:
            json.dump(gen_data, jf, ensure_ascii=False, indent=2)
        created_files.append(json_export_path)
    except Exception as e:
        log.warning("Gagal menulis arsip JSON ke %s: %s", json_export_path, e)

    for st in graduates:
        safe_name = "".join(c for c in st.nama if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        t_path = output_dir / f"{st.nim}_{safe_name}_Transkrip.png"
        i_path = output_dir / f"{st.nim}_{safe_name}_Ijazah.png"

        photo_bytes = photos_map.get(st.nim) if photos_map else None

        try:
            t_bytes = render_transkrip_png_bytes(st, photo_bytes=photo_bytes)
            i_bytes = render_ijazah_png_bytes(st, photo_bytes=photo_bytes)

            with open(t_path, "wb") as f:
                f.write(t_bytes)
            with open(i_path, "wb") as f:
                f.write(i_bytes)

            created_files.extend([t_path, i_path])
            success_count += 1
        except Exception as e:
            log.warning("Gagal export lulusan %s: %s", st.nim, e)

    return success_count, created_files


async def cmd_export_kelulusan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perintah admin /export_kelulusan [zip|sync] — Render massal seluruh ijazah & transkrip lulusan."""
    if not update.effective_user or not update.message:
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)
    row = await user_row(conn, db, uid)

    if not _is_owner(row, uid):
        await update.message.reply_text("Perintah ini hanya dapat dijalankan oleh Founder / Owner.")
        return

    args = context.args or []
    if args and args[0].lower() == "sync":
        from bot.graduation_excel import _sync_excel_into_archive
        _sync_excel_into_archive(force=True)
        all_s = get_all_students()
        grads = get_all_graduates()
        turso_count = await mirror_archive_to_turso(conn, db)
        await update.message.reply_text(
            f"🔄 <b>Sinkronisasi Arsip Kelulusan Berhasil!</b>\n\n"
            f"• Total Mahasiswa di Arsip: <b>{len(all_s)}</b>\n"
            f"• Total Mahasiswa Lulus: <b>{len(grads)}</b>\n"
            f"• File Arsip: <code>data/graduation_records.json</code>\n"
            f"• Mirror ke Turso DB: <b>{turso_count}</b> record berhasil disinkronkan.",
            parse_mode="HTML",
        )
        return

    gen_val = GENERATION_CODE.lstrip("0") or GENERATION_CODE or "1"
    output_dir = _get_output_dir(gen_val)
    zip_path = _get_zip_path(gen_val)

    graduates = get_all_graduates(generasi=gen_val)
    if not graduates:
        # Fallback ke seluruh lulusan jika data generasi belum spesifik
        graduates = get_all_graduates()

    if not graduates:
        await update.message.reply_text("Tidak ada data lulusan yang ditemukan di spreadsheet atau arsip.")
        return

    create_zip = bool(args and args[0].lower() == "zip")

    status_msg = await update.message.reply_text(
        f"⚙️ Memulai export dokumen kelulusan Gen {gen_val} (<b>{len(graduates)}</b> shishya)...\n"
        f"• Mengambil pasfoto profil shishya..."
    )

    # 1. Unduh pasfoto/avatar shishya secara paralel & efisien
    photos_map = await _fetch_photos_for_graduates(context, conn, graduates)
    with_photo_count = sum(1 for p in photos_map.values() if p)

    await status_msg.edit_text(
        f"⚙️ Memproses dokumen kelulusan Gen {gen_val} (<b>{len(graduates)}</b> shishya)...\n"
        f"• Foto ditemukan: <b>{with_photo_count}</b> / {len(graduates)}\n"
        f"• Sedang me-render ijazah & transkrip..."
    )

    # 2. Jalankan render batch di thread latar belakang agar tidak memblokir event loop Telegram
    success_count, created_files = await asyncio.to_thread(
        _sync_export_documents, graduates, output_dir, photos_map, gen_val
    )

    # 3. Mirror data lulusan ke Turso secara non-blocking
    try:
        asyncio.create_task(mirror_archive_to_turso(conn, db, graduates))
    except Exception:
        pass

    json_export_name = f"graduation_records_gen{gen_val}.json"
    msg = (
        f"✅ <b>Export Kelulusan Selesai! (Gen {gen_val})</b>\n\n"
        f"• Total Mahasiswa Lulus: <b>{len(graduates)}</b>\n"
        f"• Berhasil Digenerate: <b>{success_count}</b> mahasiswa ({success_count * 2} dokumen)\n"
        f"• Dokumen berfoto: <b>{with_photo_count}</b> mahasiswa\n"
        f"• File Data JSON: <code>{output_dir / json_export_name}</code>\n"
        f"• Arsip Master: <code>data/graduation_records.json</code>\n"
        f"• Mirror Turso DB: ✅ Tersinkronkan\n"
        f"• Folder Output: <code>{output_dir}</code>"
    )

    if create_zip and created_files:
        def _make_zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in created_files:
                    zf.write(file_path, arcname=file_path.name)
                from bot.graduation_excel import JSON_ARCHIVE_PATH
                if JSON_ARCHIVE_PATH.exists() and JSON_ARCHIVE_PATH not in created_files:
                    zf.write(JSON_ARCHIVE_PATH, arcname="graduation_records_master.json")

        await asyncio.to_thread(_make_zip)

        await status_msg.edit_text(msg + "\n\n📦 Sedang mengunggah file ZIP (termasuk berkas data JSON & pasfoto)...")
        with open(zip_path, "rb") as zf_file:
            await update.message.reply_document(
                document=zf_file,
                filename=f"Dokumen_Kelulusan_Gen{gen_val}.zip",
                caption=f"📦 Paket Lengkap Ijazah, Transkrip & Data JSON Kelulusan Gen {gen_val}",
                read_timeout=120,
                write_timeout=120,
            )
        await status_msg.delete()
    else:
        await status_msg.edit_text(
            msg + "\n\n<i>Tip: Ketik <code>/export_kelulusan zip</code> jika ingin bot mengirimkan paket ZIP langsung ke chat ini.</i>"
        )


async def cmd_sync_kelulusan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perintah admin /sync_kelulusan — Shortcut sinkronisasi Excel ke arsip JSON & Turso DB."""
    context.args = ["sync"]
    await cmd_export_kelulusan(update, context)
