import asyncio
import base64
import logging
import os
import random
import re
import string
import time

from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import *
from helper_func import (
    subscribed,
    encode,
    decode,
    get_messages,
    get_shortlink,
    get_verify_status,
    update_verify_status,
    get_exp_time,
)
from database.database import add_user, del_user, full_userbase, present_user
from shortzy import Shortzy

# Constants
WAIT_MSG = "<b>Processing ...</b>"
REPLY_ERROR = "<code>Use this command as a reply to any Telegram message without any spaces.</code>"

# Start Command
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    id = message.from_user.id
    owner_id = ADMINS

    if id == owner_id:
        await message.reply("You are the owner! Additional actions can be added here.")
        return

    if not await present_user(id):
        try:
            await add_user(id)
        except Exception as e:
            logging.error(f"Failed to add user {id}: {e}")

    verify_status = await get_verify_status(id)
    if verify_status["is_verified"] and VERIFY_EXPIRE < (time.time() - verify_status["verified_time"]):
        await update_verify_status(id, is_verified=False)

    if "verify_" in message.text:
        _, token = message.text.split("_", 1)
        if verify_status["verify_token"] != token:
            return await message.reply("Your token is invalid or expired. Try again by clicking /start.")
        await update_verify_status(id, is_verified=True, verified_time=time.time())
        await message.reply("Your token successfully verified and is valid for 24 hours.")
        return

    if len(message.text) > 7 and verify_status["is_verified"]:
        try:
            base64_string = message.text.split(" ", 1)[1]
            _string = await decode(base64_string)
            argument = _string.split("-")

            if len(argument) == 3:
                start, end = map(int, [int(argument[1]) / abs(client.db_channel.id), int(argument[2]) / abs(client.db_channel.id)])
                ids = range(start, end + 1) if start <= end else list(reversed(range(end, start + 1)))
            elif len(argument) == 2:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            else:
                ids = []

            temp_msg = await message.reply(WAIT_MSG)
            messages = await get_messages(client, ids)
            await temp_msg.delete()

            for msg in messages:
                caption = (CUSTOM_CAPTION.format(previouscaption=msg.caption.html or "", filename=msg.document.file_name)
                           if CUSTOM_CAPTION and msg.document else msg.caption.html or "")
                try:
                    await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=None if DISABLE_CHANNEL_BUTTON else msg.reply_markup,
                        protect_content=PROTECT_CONTENT,
                    )
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                except Exception as e:
                    logging.error(f"Error copying message {msg.id}: {e}")

        except Exception as e:
            logging.error(f"Error handling start command: {e}")
            await message.reply("Something went wrong!")
        return

    if verify_status["is_verified"]:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("About Me", callback_data="about"), InlineKeyboardButton("Close", callback_data="close")]
        ])
        await message.reply_photo(
            photo=START_PIC,
            caption=START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=f"@{message.from_user.username}" if message.from_user.username else None,
                mention=message.from_user.mention,
                id=message.from_user.id,
            ),
            reply_markup=reply_markup,
        )
    else:
        token = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        await update_verify_status(id, verify_token=token, link="")
        link = await get_shortlink(SHORTLINK_URL, SHORTLINK_API, f"https://telegram.dog/{client.username}?start=verify_{token}")
        btn = [
            [InlineKeyboardButton("Click here", url=link)],
            [InlineKeyboardButton("How to use the bot", url="https://t.me/neprosz/3")]
        ]
        await message.reply(
            f"Your Ads token has expired. Refresh your token to continue.\n\n"
            f"Token Timeout: {get_exp_time(VERIFY_EXPIRE)}\n\n"
            f"This is an ads token. After passing an ad, you can use the bot for 24 hours.",
            reply_markup=InlineKeyboardMarkup(btn),
        )


# User Count Command
@Bot.on_message(filters.command("users") & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")


# Broadcast Command
@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total, successful, blocked, deleted, unsuccessful = 0, 0, 0, 0, 0

        pls_wait = await message.reply("<i>Broadcasting Message... This will take some time.</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except Exception as e:
                logging.error(f"Error broadcasting to {chat_id}: {e}")
                unsuccessful += 1
            total += 1

        status = (f"<b><u>Broadcast Completed</u></b>\n\n"
                  f"Total Users: <code>{total}</code>\n"
                  f"Successful: <code>{successful}</code>\n"
                  f"Blocked Users: <code>{blocked}</code>\n"
                  f"Deleted Accounts: <code>{deleted}</code>\n"
                  f"Unsuccessful: <code>{unsuccessful}</code>")
        await pls_wait.edit(status)
    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()