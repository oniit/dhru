"""Parse /setrole <role> dengan @mention / reply (banyak user)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from telegram import Message
from telegram.constants import MessageEntityType


@dataclass
class ParsedSetrole:
    role: str
    target_ids: set[int]
    mention_usernames: list[str]
    is_mass: bool = False
    mass_target: str | None = None


def parse_setrole_command(message: Message) -> ParsedSetrole | None:
    text = message.text or ""
    m = re.match(r"^/setrole(?:@\S+)?\s+(\S+)\s*", text)
    if not m:
        return None
    role = m.group(1).lower().strip()
    cmd_end = m.end()

    target_ids: set[int] = set()
    mention_usernames: list[str] = []

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if not ru.is_bot:
            target_ids.add(ru.id)

    if message.entities:
        for e in message.entities:
            if e.type == MessageEntityType.TEXT_MENTION and e.user and not e.user.is_bot:
                if e.offset >= cmd_end:
                    target_ids.add(e.user.id)
            elif e.type == MessageEntityType.MENTION:
                if e.offset >= cmd_end:
                    chunk = text[e.offset : e.offset + e.length].lstrip("@")
                    if chunk:
                        mention_usernames.append(chunk)

    if not target_ids and not mention_usernames:
        tail = text[cmd_end:].strip().lower()
        first_token = tail.split()[0] if tail else ""
        if first_token in {"all", "massal", "shishya", "student", "students", "shishyas", "semua", "bem"}:
            return ParsedSetrole(
                role=role,
                target_ids=set(),
                mention_usernames=[],
                is_mass=True,
                mass_target=first_token,
            )
        return None

    return ParsedSetrole(
        role=role,
        target_ids=target_ids,
        mention_usernames=mention_usernames,
        is_mass=False,
        mass_target=None,
    )
