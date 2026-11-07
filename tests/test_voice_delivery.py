import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram.constants import ChatAction

from english_bot.voice_delivery import send_voice_reply


class VoiceDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        self.bot = SimpleNamespace(send_chat_action=AsyncMock())
        self.message = SimpleNamespace(
            chat_id=1, reply_text=AsyncMock(return_value=self.status),
            reply_voice=AsyncMock(), get_bot=Mock(return_value=self.bot),
        )

    async def test_notice_is_visible_while_generation_runs_and_removed_after_voice(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def synthesise(text):
            started.set()
            await release.wait()
            return b"mp3"

        task = asyncio.create_task(send_voice_reply(self.message, "Hello", synthesise, activity_interval=0.01))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertIn("Preparing", self.message.reply_text.call_args.args[0])
            self.message.reply_voice.assert_not_awaited()
            self.status.delete.assert_not_awaited()
            await asyncio.sleep(0.05)
            self.assertTrue(any(call.args[1] == ChatAction.RECORD_VOICE for call in self.bot.send_chat_action.call_args_list))
            self.status.edit_text.assert_awaited_once()
            self.assertIn("Still preparing", self.status.edit_text.call_args.args[0])
        finally:
            release.set()
            await task
        self.message.reply_voice.assert_awaited_once()
        self.status.delete.assert_awaited_once()
        self.assertEqual(self.bot.send_chat_action.call_args.args[1], ChatAction.UPLOAD_VOICE)
        sent_audio = self.message.reply_voice.call_args.kwargs["voice"]
        self.assertEqual(sent_audio.name, "reply.mp3")
        self.assertEqual(sent_audio.getvalue(), b"mp3")

    async def test_failure_replaces_pending_notice(self):
        with self.assertLogs("english_bot.voice_delivery", level="WARNING"):
            await send_voice_reply(self.message, "Hello", AsyncMock(side_effect=RuntimeError()))
        self.assertIn("couldn't send", self.status.edit_text.call_args.args[0])
        self.message.reply_voice.assert_not_awaited()
        self.status.delete.assert_not_awaited()

    async def test_failed_activity_indicator_does_not_prevent_voice(self):
        self.bot.send_chat_action.side_effect = RuntimeError()
        await send_voice_reply(self.message, "Hello", AsyncMock(return_value=b"mp3"))
        self.message.reply_voice.assert_awaited_once()
        self.status.delete.assert_awaited_once()
