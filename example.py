import os, time
from vrzdk import router, run, bot
from aiogram.types import Message, MessageReactionUpdated
from aiogram.filters import CommandStart

@router.message(CommandStart())
async def start_cmd(msg: Message):
    await msg.answer(f"{os.path.basename(__file__)} aktif!")

TRIGGER_START = {
    "mulai!",
    "1"
}
TRIGGER_STOP = {
    "stop!",
    "stop.",
    "stop",
    "berhenti!",
    "berhenti.",
    "berhenti",
    "selesai!",
    "selesai.",
    "selesai"
}

ALLOWED_USER_IDS = {8568632044, 5958155948}

game_active_by_chat = {}
start_message_id_by_chat = {}
reaction_data_by_chat = {}

@router.message()
async def handle_text(msg: Message):
    global game_active_by_chat, start_message_id_by_chat, reaction_data_by_chat

    if msg.from_user.id not in ALLOWED_USER_IDS:
        return

    text = msg.text.lower().strip()

    if text in TRIGGER_START:
        chat_id = msg.chat.id
        game_active_by_chat[chat_id] = True
        start_message_id_by_chat[chat_id] = msg.message_id
        reaction_data_by_chat[chat_id] = {}
        return

    if text in TRIGGER_STOP:
        chat_id = msg.chat.id
        game_active_by_chat[chat_id] = False
        reaction_data = reaction_data_by_chat.get(chat_id, {})

        if not reaction_data:
            await msg.reply("belum ada react yg masuk.")
            return

        winner_msg_id = None
        max_react = -1
        fastest_ts = float("inf")

        for msg_id, data in reaction_data.items():
            if data["count"] > max_react:
                winner_msg_id = msg_id
                max_react = data["count"]
                fastest_ts = data["first_react_ts"]
            elif data["count"] == max_react:
                if data["first_react_ts"] < fastest_ts:
                    winner_msg_id = msg_id
                    fastest_ts = data["first_react_ts"]

        await bot.send_message(
            chat_id=msg.chat.id,
            text=f"⠀⠀⠀𖠹 ˙˙˙ congrats!  ༨𐂥⠀\n         🔥 total react: {max_react}",
            reply_to_message_id=winner_msg_id
        )

        return
        
@router.message_reaction()
async def handle_reaction(update: MessageReactionUpdated):
    if update.chat.id is None:
        return

    chat_id = update.chat.id
    if not game_active_by_chat.get(chat_id, False):
        return

    msg_id = update.message_id
    start_message_id = start_message_id_by_chat.get(chat_id)
    if start_message_id is None or msg_id <= start_message_id:
        return

    delta = len(update.new_reaction) - len(update.old_reaction)
    if delta == 0:
        return

    reaction_data = reaction_data_by_chat.setdefault(chat_id, {})

    if msg_id not in reaction_data:
        reaction_data[msg_id] = {
            "count": 0,
            "first_react_ts": time.time()
        }

    reaction_data[msg_id]["count"] += delta

run()