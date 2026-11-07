"""Make the wait for local speech visible in Telegram."""

import asyncio
import logging
from contextlib import suppress
from io import BytesIO

from telegram.constants import ChatAction

LOG = logging.getLogger(__name__)


async def send_voice_reply(message, text, synthesise, *, activity_interval=4):
    status = None
    activity = None
    failed = False

    async def show_activity():
        ticks = 0
        while True:
            with suppress(Exception):
                await message.get_bot().send_chat_action(message.chat_id, ChatAction.RECORD_VOICE)
            await asyncio.sleep(activity_interval)
            ticks += 1
            if ticks == 3:
                with suppress(Exception):
                    await status.edit_text(
                        "🔊 Still preparing your voice reply…\n\n"
                        "Longer replies take a little more time. You can read the text above while you wait."
                    )

    try:
        status = await message.reply_text(
            "🔊 Preparing your voice reply…\n\n"
            "The text is ready above. Your audio will follow here."
        )
        activity = asyncio.create_task(show_activity())
        audio = BytesIO(await synthesise(text))
        audio.name = "reply.mp3"
        with suppress(Exception):
            await message.get_bot().send_chat_action(message.chat_id, ChatAction.UPLOAD_VOICE)
        await message.reply_voice(voice=audio, caption="🔊 Spoken reply · AI voice")
    except Exception as error:
        failed = True
        LOG.warning("Voice output failed (%s)", type(error).__name__)
    finally:
        if activity:
            activity.cancel()
            with suppress(asyncio.CancelledError):
                await activity

    if failed:
        notice = "I couldn't send the voice reply this time. Your text reply is above. Please try again."
        try:
            if status:
                await status.edit_text(notice)
            else:
                await message.reply_text(notice)
        except Exception:
            LOG.warning("Could not send voice failure notice")
    elif status:
        try:
            await status.delete()
        except Exception:
            with suppress(Exception):
                await status.edit_text("🔊 Voice reply sent below.")
