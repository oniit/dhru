"""Parse /add command: nominal, targets (reply + mentions), description."""

from __future__ import annotations

import re
from dataclasses import dataclass

from telegram import Message
from telegram.constants import MessageEntityType


@dataclass
class ParsedAdd:
    amount: int
    target_ids: set[int]
    mention_usernames: list[str]  # without @, for DB lookup
    description: str


def parse_add_command(message: Message) -> ParsedAdd | None:
    text = message.text or ""
    m = re.match(r"^/add(?:@\S+)?\s+(-?\d+)\s*", text)
    if not m:
        return None
    amount = int(m.group(1))
    end_cmd = m.end()
    tail = text[end_cmd:].strip()

    target_ids: set[int] = set()
    mention_usernames: list[str] = []

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if not ru.is_bot:
            target_ids.add(ru.id)

    if message.entities:
        for e in message.entities:
            if e.type == MessageEntityType.TEXT_MENTION and e.user and not e.user.is_bot:
                target_ids.add(e.user.id)
            elif e.type == MessageEntityType.MENTION:
                chunk = text[e.offset : e.offset + e.length].lstrip("@")
                if chunk:
                    mention_usernames.append(chunk)

    description = ""
    if " | " in tail:
        _, description = tail.split(" | ", 1)
        description = description.strip()
    elif tail.strip().startswith("|"):
        description = tail.split("|", 1)[-1].strip()
    else:
        description = re.sub(r"@\w+", "", tail)
        description = re.sub(r"\s+", " ", description).strip()

    if len(description) < 1:
        return None

    return ParsedAdd(
        amount=amount,
        target_ids=target_ids,
        mention_usernames=mention_usernames,
        description=description,
    )
