"""
Handler untuk perintah /pfp.
Mem-forward postingan dari channel Telegram ke KEEP_CH_ID (single atau rentang 'link to link').
Menampilkan tutorial dan sub-menu khusus owner (pfp daily & pfp weekly).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.database import Database
from bot.settings import KEEP_CH_ID, OWNER_ID, is_owner
from bot.timefmt import TZ, get_today_wib

log = logging.getLogger(__name__)


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data.get("db") or context.bot_data.get("db")


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data.get("conn") or context.bot_data.get("conn")


def parse_telegram_post_link(link: str) -> tuple[str | int, int] | None:
    """
    Mengurai tautan postingan channel Telegram.
    Mengembalikan (channel_identifier, message_id) atau None jika tidak valid.
    channel_identifier berupa:
      - '@username' untuk channel publik
      - -100xxxxxxxxxx (int) untuk channel privat
    Mendukung format standar (t.me/...), preview publik (t.me/s/...), dan privat (t.me/c/...).
    """
    if not link:
        return None
    raw = link.strip().strip("<>()[]\"'`").strip()
    if "?" in raw:
        raw = raw.split("?", 1)[0]
    if "#" in raw:
        raw = raw.split("#", 1)[0]
    raw = raw.rstrip("/")

    # Channel privat: t.me/c/<channel_id>/<msg_id> atau t.me/s/c/<channel_id>/<msg_id>
    m_priv = re.search(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?c/(\d+)/(\d+)",
        raw,
        re.IGNORECASE,
    )
    if m_priv:
        ch_num = m_priv.group(1)
        msg_id = int(m_priv.group(2))
        return int(f"-100{ch_num}"), msg_id

    # Channel publik: t.me/<channel_username>/<msg_id> atau t.me/s/<channel_username>/<msg_id>
    m_pub = re.search(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?([a-zA-Z0-9_]+)/(\d+)",
        raw,
        re.IGNORECASE,
    )
    if m_pub:
        username = m_pub.group(1).lower()
        if username not in ("c", "s", "joinchat", "share", "addstickers"):
            msg_id = int(m_pub.group(2))
            return f"@{username}", msg_id

    return None


def parse_pfp_args(args: list[str]) -> tuple[str, any]:
    """
    Membedah argumen dari perintah /pfp.
    Returns:
      - ('TUTOR', None) jika argumen kosong
      - ('DAILY', None) jika 'daily'
      - ('WEEKLY', None) jika 'weekly'
      - ('RANGE', (link1, link2)) jika ada pemisah rentang ('to', '-', 'sampai', 's/d', 'sd')
      - ('SINGLE', link) jika tautan tunggal
      - ('INVALID', None) jika tidak dikenali
    """
    raw = " ".join(args).strip()
    if not raw:
        return "TUTOR", None

    low = raw.lower()
    if low == "daily":
        return "DAILY", None
    if low == "weekly":
        return "WEEKLY", None

    parts = re.split(r"\s+(?:to|-|sampai|s/d|sd)\s+", raw, flags=re.IGNORECASE)
    if len(parts) == 2:
        return "RANGE", (parts[0].strip(), parts[1].strip())
    elif len(parts) == 1:
        return "SINGLE", parts[0].strip()
    else:
        return "INVALID", None


async def _forward_via_userbot_ipc(
    conn, db: Database, from_chat: str | int, start_id: int, end_id: int
) -> int:
    """Fallback mem-forward pesan menggunakan userbot (checker.py) via IPC."""
    if not conn or not db:
        return 0
    try:
        req_id = await db.create_userbot_request(
            conn, "0", f"FORWARD:{from_chat}:{start_id}:{end_id}"
        )
        for _ in range(12):  # Polling hingga maksimal 6 detik
            await asyncio.sleep(0.5)
            req_row = await db.get_userbot_request(conn, req_id)
            if req_row and req_row["status"] == "DONE":
                res = json.loads(req_row["result"])
                return int(res.get("forwarded", 0))
            if req_row and req_row["status"] == "ERROR":
                break
    except Exception as e:
        log.warning("Gagal forward via userbot IPC: %s", e)
    return 0


async def forward_posts_to_keep(
    bot,
    conn,
    db: Database,
    keep_ch_id: int,
    from_chat: str | int,
    start_id: int,
    end_id: int,
) -> tuple[int, str | None]:
    """
    Mem-forward postingan dari channel ke KEEP_CH_ID.
    Mendukung pesan tunggal atau rentang pesan.
    Returns: (forwarded_count, error_msg)
    """
    if start_id == end_id:
        try:
            await bot.forward_message(
                chat_id=keep_ch_id,
                from_chat_id=from_chat,
                message_id=start_id,
            )
            return 1, None
        except Exception as e:
            err_str = str(e)
            log.warning("Bot single forward failed for %s:%s: %s", from_chat, start_id, err_str)
            if conn and db:
                ipc_count = await _forward_via_userbot_ipc(
                    conn, db, from_chat, start_id, end_id
                )
                if ipc_count > 0:
                    return ipc_count, None
            return 0, err_str

    all_ids = list(range(start_id, end_id + 1))
    forwarded_count = 0
    bot_failed = False

    try:
        # Batch forward (Telegram Bot API mendukung hingga 100 ID per panggilan)
        res = await bot.forward_messages(
            chat_id=keep_ch_id,
            from_chat_id=from_chat,
            message_ids=all_ids,
        )
        forwarded_count = len(res)
        return forwarded_count, None
    except Exception as fe:
        fe_str = str(fe).lower()
        log.warning("Batch forward failed (%s), trying individual fallback", fe)
        if "chat not found" in fe_str or "forbidden" in fe_str or "bot was blocked" in fe_str:
            bot_failed = True
        else:
            for mid in all_ids:
                try:
                    await bot.forward_message(
                        chat_id=keep_ch_id,
                        from_chat_id=from_chat,
                        message_id=mid,
                    )
                    forwarded_count += 1
                    await asyncio.sleep(0.15)
                except Exception as se:
                    se_str = str(se).lower()
                    if "chat not found" in se_str or "forbidden" in se_str:
                        bot_failed = True
                        break
                    # Abaikan pesan yang terhapus/tidak ada di rentang

    if forwarded_count == 0 and conn and db:
        ipc_count = await _forward_via_userbot_ipc(conn, db, from_chat, start_id, end_id)
        if ipc_count > 0:
            return ipc_count, None

    err_msg = None if forwarded_count > 0 else "Gagal mem-forward pesan."
    return forwarded_count, err_msg


def get_pfp_tutorial_text(is_user_owner: bool) -> tuple[str, InlineKeyboardMarkup | None]:
    """Menghasilkan teks panduan dan markup tombol untuk perintah /pfp."""
    text = (
        "📖 <b>Panduan Penggunaan Perintah /pfp</b>\n\n"
        "Perintah <code>/pfp</code> dapat digunakan di private chat maupun grup "
        "untuk mem-forward postingan dari channel Telegram ke channel penyimpanan (KEEP).\n\n"
        "<b>Format Perintah:</b>\n"
        "1️⃣ <b>Forward 1 Post:</b>\n"
        "<code>/pfp &lt;link_post&gt;</code>\n"
        "<i>Contoh:</i> <code>/pfp https://t.me/namachannel/123</code>\n\n"
        "2️⃣ <b>Forward Banyak Post (Rentang):</b>\n"
        "<code>/pfp &lt;link_awal&gt; to &lt;link_akhir&gt;</code>\n"
        "<i>Contoh:</i> <code>/pfp https://t.me/namachannel/100 to https://t.me/namachannel/120</code>\n\n"
        "<b>Catatan:</b>\n"
        "• Setiap 1 post yang berhasil diforward otomatis mendapatkan <b>+1 Agra</b>.\n"
        "• Tautan awal dan akhir harus berasal dari channel yang sama.\n"
        "• Maksimal forward 100 post dalam sekali perintah.\n"
        "• Mendukung link publik (<code>t.me/channel/123</code>) dan privat (<code>t.me/c/12345/123</code>)."
    )

    if is_user_owner:
        text += (
            "\n\n👑 <b>Sub Menu Khusus Owner:</b>\n"
            "• <b>PFP Daily:</b> Rekap pengguna yang forward post hari ini beserta jumlahnya.\n"
            "• <b>PFP Weekly:</b> Rekapan ringkas statistik forward 7 hari terakhir.\n"
            "<i>(Gunakan tombol di bawah atau ketik <code>/pfp daily</code> / <code>/pfp weekly</code>)</i>"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📊 PFP Daily", callback_data="pfp:daily"),
                    InlineKeyboardButton("📅 PFP Weekly", callback_data="pfp:weekly"),
                ]
            ]
        )
        return text, keyboard

    return text, None


async def get_pfp_daily_content(conn, db: Database) -> tuple[str, InlineKeyboardMarkup]:
    """Menghasilkan konten rekap harian PFP untuk hari ini."""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="pfp:daily"),
                InlineKeyboardButton("📅 PFP Weekly", callback_data="pfp:weekly"),
            ],
            [
                InlineKeyboardButton("🔙 Panduan /pfp", callback_data="pfp:menu"),
            ],
        ]
    )

    if not conn or not db:
        return "⚠️ <i>Database belum terhubung.</i>", keyboard

    today = get_today_wib()
    start_ts = datetime.combine(today, datetime.min.time(), tzinfo=TZ).timestamp()
    end_ts = datetime.combine(today, datetime.max.time(), tzinfo=TZ).timestamp()

    rows = await db.get_pfp_daily_stats(conn, start_ts, end_ts)

    lines = [
        "📊 <b>Laporan PFP Daily (Hari Ini)</b>",
        f"📅 <i>{today.strftime('%d/%m/%Y')}</i>\n",
    ]

    if not rows:
        lines.append("<i>Belum ada pengguna yang mem-forward post hari ini.</i>")
    else:
        lines.append("<b>Daftar Pengguna:</b>")
        total_posts_sum = 0
        truncated = False
        current_len = sum(len(l) for l in lines)
        for idx, r in enumerate(rows, start=1):
            fn = (r.get("first_name") or "").strip()
            un = (r.get("username") or "").strip()
            uid = r["user_id"]
            posts = int(r["total_posts"] or 0)
            cmds = int(r["total_commands"] or 0)
            total_posts_sum += posts

            if un:
                user_lbl = f"<b>{html.escape(fn or un)}</b> (@{html.escape(un)})"
            elif fn:
                user_lbl = f"<b>{html.escape(fn)}</b> (<code>{uid}</code>)"
            else:
                user_lbl = f"Pengguna (<code>{uid}</code>)"

            entry_line = f"{idx}. {user_lbl} — <b>{posts}</b> post ({cmds}x fwd)"
            if not truncated:
                if current_len + len(entry_line) > 3300:
                    remaining = len(rows) - idx + 1
                    lines.append(f"<i>...dan {remaining} pengguna lainnya.</i>")
                    truncated = True
                else:
                    lines.append(entry_line)
                    current_len += len(entry_line)

        lines.append("\n━━━━━━━━━━━━━━━━━━━")
        lines.append(f"👥 <b>Total Pengguna:</b> {len(rows)} orang")
        lines.append(f"📦 <b>Total Post Ter-forward:</b> {total_posts_sum} post")

    return "\n".join(lines), keyboard


async def get_pfp_weekly_content(conn, db: Database) -> tuple[str, InlineKeyboardMarkup]:
    """Menghasilkan konten rekap mingguan PFP untuk 7 hari terakhir."""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="pfp:weekly"),
                InlineKeyboardButton("📊 PFP Daily", callback_data="pfp:daily"),
            ],
            [
                InlineKeyboardButton("🔙 Panduan /pfp", callback_data="pfp:menu"),
            ],
        ]
    )

    if not conn or not db:
        return "⚠️ <i>Database belum terhubung.</i>", keyboard

    today = get_today_wib()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    start_ts = datetime.combine(days[0], datetime.min.time(), tzinfo=TZ).timestamp()
    end_ts = datetime.combine(days[-1], datetime.max.time(), tzinfo=TZ).timestamp()

    rows = await db.get_pfp_weekly_stats(conn, start_ts, end_ts)

    day_map: dict[any, dict] = {d: {"users": set(), "posts": 0} for d in days}
    for r in rows:
        row_date = datetime.fromtimestamp(r["created_at"], tz=TZ).date()
        if row_date in day_map:
            day_map[row_date]["users"].add(r["user_id"])
            day_map[row_date]["posts"] += int(r["forwarded_count"] or 0)

    lines = [
        "📅 <b>Rekapan PFP Weekly (7 Hari Terakhir)</b>",
        f"Periode: <i>{days[0].strftime('%d/%m/%Y')} – {days[-1].strftime('%d/%m/%Y')}</i>\n",
    ]

    all_users = set()
    total_week_posts = 0

    for d in days:
        u_count = len(day_map[d]["users"])
        p_count = day_map[d]["posts"]
        all_users.update(day_map[d]["users"])
        total_week_posts += p_count

        d_str = d.strftime("%d/%m/%Y")
        tag = " <i>(Hari Ini)</i>" if d == today else ""

        if p_count > 0:
            lines.append(f"• <b>{d_str}{tag}:</b> {u_count} user • <b>{p_count}</b> post")
        else:
            lines.append(f"• <b>{d_str}{tag}:</b> — (0 post)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append(f"👥 <b>Total Pengguna Unik:</b> {len(all_users)} orang")
    lines.append(f"📦 <b>Total Seluruh Post:</b> {total_week_posts} post")

    return "\n".join(lines), keyboard


async def cmd_pfp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler utama perintah /pfp."""
    if not update.effective_message or not update.effective_user:
        return

    uid = update.effective_user.id
    conn = _conn(context)
    db = _db(context)

    action, data = parse_pfp_args(context.args or [])

    # Sub-perintah: Daily
    if action == "DAILY":
        if not is_owner(uid):
            await update.effective_message.reply_text(
                "⛔ Perintah ini hanya dapat diakses oleh Owner.",
                parse_mode="HTML",
            )
            return
        text, kb = await get_pfp_daily_content(conn, db)
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    # Sub-perintah: Weekly
    if action == "WEEKLY":
        if not is_owner(uid):
            await update.effective_message.reply_text(
                "⛔ Perintah ini hanya dapat diakses oleh Owner.",
                parse_mode="HTML",
            )
            return
        text, kb = await get_pfp_weekly_content(conn, db)
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    # Tampilkan Tutorial jika tanpa argumen
    if action == "TUTOR":
        text, kb = get_pfp_tutorial_text(is_owner(uid))
        await update.effective_message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return

    # Validasi tautan
    if action == "SINGLE":
        parsed = parse_telegram_post_link(data)
        if not parsed:
            await update.effective_message.reply_text(
                "❌ <b>Format tautan tidak valid!</b>\n"
                "Pastikan tautan mengarah ke postingan channel Telegram.\n\n"
                "<i>Contoh:</i> <code>/pfp https://t.me/channel/123</code>",
                parse_mode="HTML",
            )
            return
        channel_id, msg_id = parsed
        start_id = end_id = msg_id
        total_requested = 1

    elif action == "RANGE":
        link1, link2 = data
        parsed1 = parse_telegram_post_link(link1)
        parsed2 = parse_telegram_post_link(link2)

        if not parsed1 or not parsed2:
            await update.effective_message.reply_text(
                "❌ <b>Format tautan rentang tidak valid!</b>\n"
                "Pastikan kedua tautan mengarah ke postingan channel Telegram.\n\n"
                "<i>Contoh:</i> <code>/pfp https://t.me/channel/100 to https://t.me/channel/120</code>",
                parse_mode="HTML",
            )
            return

        if parsed1[0] != parsed2[0]:
            await update.effective_message.reply_text(
                "❌ <b>Kedua tautan harus berasal dari channel yang sama!</b>",
                parse_mode="HTML",
            )
            return

        channel_id = parsed1[0]
        start_id = min(parsed1[1], parsed2[1])
        end_id = max(parsed1[1], parsed2[1])
        total_requested = end_id - start_id + 1

        if total_requested > 100:
            await update.effective_message.reply_text(
                f"❌ Rentang forward maksimal adalah <b>100 post</b> sekaligus.\n"
                f"Rentang yang diminta: <b>{total_requested} post</b>.",
                parse_mode="HTML",
            )
            return
    else:
        await update.effective_message.reply_text(
            "❌ Format perintah tidak dikenali.\nKetik <code>/pfp</code> untuk melihat panduan.",
            parse_mode="HTML",
        )
        return

    if not KEEP_CH_ID:
        await update.effective_message.reply_text(
            "❌ Channel penyimpanan (<code>KEEP_CH_ID</code>) belum dikonfigurasi di bot.",
            parse_mode="HTML",
        )
        return

    status_msg = None
    try:
        status_msg = await update.effective_message.reply_text(
            f"⏳ <i>Sedang mem-forward {total_requested} pesan ke channel penyimpanan...</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning("Gagal mengirim pesan status awal /pfp: %s", e)

    forwarded_count, err = await forward_posts_to_keep(
        context.bot,
        conn,
        db,
        KEEP_CH_ID,
        channel_id,
        start_id,
        end_id,
    )

    if forwarded_count > 0:
        if conn and db:
            chat_id = update.effective_chat.id if update.effective_chat else uid
            await db.log_pfp_forward(
                conn=conn,
                user_id=uid,
                chat_id=chat_id,
                channel_id=str(channel_id),
                first_msg_id=start_id,
                last_msg_id=end_id,
                forwarded_count=forwarded_count,
                created_at=time.time(),
            )
            # Reward: 1 post = 1 Agra (tanpa batas)
            try:
                await db.add_agra(
                    conn=conn,
                    target_id=uid,
                    actor_id=uid,
                    amount=forwarded_count,
                    description=f"Reward forward {forwarded_count} post (/pfp)",
                    chat_id=chat_id,
                    message_id=None,
                )
            except Exception as e:
                log.warning("Gagal menambahkan Agra untuk pfp forward user %s: %s", uid, e)

        if total_requested == 1:
            reply_text = "✅ <b>1 post</b> berhasil diforward ke channel penyimpanan. (<b>+1 Agra</b>)"
        else:
            reply_text = (
                f"✅ Berhasil mem-forward <b>{forwarded_count}</b> dari <b>{total_requested}</b> "
                f"post ke channel penyimpanan. (<b>+{forwarded_count} Agra</b>)"
            )
        if status_msg:
            try:
                await status_msg.edit_text(reply_text, parse_mode="HTML")
            except Exception:
                await update.effective_message.reply_text(reply_text, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(reply_text, parse_mode="HTML")
    else:
        err_detail = f"\n<i>Detail: {html.escape(str(err))}</i>" if err else ""
        fail_text = (
            "❌ <b>Gagal mem-forward post.</b>\n"
            "Pastikan channel sumber bersifat publik atau bot memiliki izin akses, "
            f"dan konten tidak dibatasi dari forwarding.{err_detail}"
        )
        if status_msg:
            try:
                await status_msg.edit_text(fail_text, parse_mode="HTML")
            except Exception:
                await update.effective_message.reply_text(fail_text, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(fail_text, parse_mode="HTML")


async def cb_pfp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """CallbackQueryHandler untuk menu interaktif /pfp."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    uid = update.effective_user.id
    if not is_owner(uid):
        await query.answer("⛔ Hanya owner yang dapat mengakses menu ini.", show_alert=True)
        return

    data = query.data or ""
    conn = _conn(context)
    db = _db(context)

    try:
        if data == "pfp:daily":
            text, kb = await get_pfp_daily_content(conn, db)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        elif data == "pfp:weekly":
            text, kb = await get_pfp_weekly_content(conn, db)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        elif data == "pfp:menu":
            text, kb = get_pfp_tutorial_text(is_owner(uid))
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            log.warning("Gagal edit message %s: %s", data, e)
    except Exception as e:
        log.warning("Error in cb_pfp %s: %s", data, e)
    finally:
        try:
            await query.answer()
        except Exception:
            pass
