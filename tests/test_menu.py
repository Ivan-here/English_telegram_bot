import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from english_bot.bot import create_application
from english_bot.config import Settings
from english_bot.store import Store


class MenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        settings = Settings("123:ABC", "key", "chat", "audio", ":memory:", frozenset({1}))
        with patch("english_bot.bot.Store", return_value=self.store), patch("english_bot.bot.Tutor") as tutor:
            self.app = create_application(settings)
            self.tutor = tutor.return_value
            self.tutor.respond = AsyncMock(return_value="That is an interesting idea.")
            self.tutor.coach = AsyncMock(return_value="Progress\nGood work.\n\nPractice\nTry one more sentence.")
            self.tutor.close = AsyncMock()
        self.handler = next(h for h in self.app.handlers[0] if isinstance(h, CallbackQueryHandler))
        self.message = SimpleNamespace(reply_text=AsyncMock(), chat_id=1, message_id=10)
        self.query = SimpleNamespace(data="", answer=AsyncMock(), edit_message_text=AsyncMock(), message=self.message)
        self.update = SimpleNamespace(callback_query=self.query, effective_message=self.message,
                                      effective_user=SimpleNamespace(id=1), effective_chat=SimpleNamespace(type="private"))
        self.context = SimpleNamespace(bot=SimpleNamespace(send_chat_action=AsyncMock()))

    def tearDown(self):
        self.store.close()

    async def tap(self, data):
        self.query.data = "ui:" + data
        await self.handler.callback(self.update, self.context)

    async def test_settings_buttons_persist_and_update_in_place(self):
        await self.tap("voice:1")
        await self.tap("transcript:1")
        await self.tap("level:B2")
        self.assertEqual(self.store.preferences(1), (True, "B2"))
        self.assertTrue(self.store.show_transcript(1))
        self.assertFalse(self.store.show_transcript(2))
        self.message.reply_text.assert_not_awaited()
        self.assertEqual(self.query.edit_message_text.await_count, 3)
        self.assertEqual(self.query.edit_message_text.call_args.kwargs["parse_mode"], "HTML")
        await self.tap("voice:0")
        self.assertEqual(self.store.preferences(1), (False, "B2"))
        self.assertTrue(self.store.show_transcript(1))

    async def test_navigation_and_feedback_empty_state(self):
        for screen in ["home", "help", "topics", "topic:history", "privacy", "levels"]:
            await self.tap(screen)
        self.assertEqual(self.query.edit_message_text.await_count, 6)
        await self.tap("feedback")
        self.assertIn("Your feedback starts here", self.message.reply_text.call_args.args[0])

    async def test_callback_allowlist_is_enforced(self):
        self.update.effective_user.id = 2
        await self.tap("voice:1")
        self.assertEqual(self.store.preferences(2), (False, "B1"))
        self.query.edit_message_text.assert_not_awaited()
        self.query.answer.assert_awaited_once()

    async def test_topic_refresh_uses_current_rotation(self):
        with patch("english_bot.topics.time.time", return_value=1799):
            await self.tap("topic:learning")
            first = self.query.edit_message_text.call_args.args[0]
        with patch("english_bot.topics.time.time", return_value=1800):
            await self.tap("topic:learning")
            second = self.query.edit_message_text.call_args.args[0]
        self.assertNotEqual(first, second)
        self.assertIn("A question to get started", second)

    async def test_answer_includes_the_selected_starter_in_model_context(self):
        await self.tap("topic:nature")
        self.message.voice = None
        self.message.text = "I enjoy walking in a forest."
        chat = next(h for h in self.app.handlers[0] if isinstance(h, MessageHandler))
        await chat.callback(self.update, self.context)
        history = self.tutor.respond.call_args.args[0]
        self.assertEqual(history[-2]["role"], "assistant")
        self.assertTrue(history[-2]["content"].endswith("?"))
        self.assertEqual(history[-1]["content"], self.message.text)

    async def test_open_topic_is_automatically_refreshed_at_the_next_tick(self):
        await self.tap("topic:daily")
        app = SimpleNamespace(bot=AsyncMock())
        with patch("english_bot.bot.asyncio.sleep", side_effect=[None, asyncio.CancelledError]), patch("english_bot.topics.time.time", return_value=1800):
            await self.app.post_init(app)
            task = next(t for t in asyncio.all_tasks() if t.get_coro().__name__ == "refresh_topics")
            with self.assertRaises(asyncio.CancelledError):
                await task
        app.bot.edit_message_text.assert_awaited_once()
        self.assertEqual(app.bot.edit_message_text.call_args.kwargs["message_id"], 10)
        await self.app.post_shutdown(app)

    async def test_refresh_changes_question_immediately_and_answer_uses_it(self):
        with patch("english_bot.topics.time.time", return_value=0):
            await self.tap("topic:daily")
            first = self.query.edit_message_text.call_args.args[0]
            await self.tap("refresh:daily:0")
            second = self.query.edit_message_text.call_args.args[0]
            self.assertNotEqual(first, second)
            # Even a second fast tap on the old button must advance again.
            await self.tap("refresh:daily:0")
            third = self.query.edit_message_text.call_args.args[0]
            self.assertNotEqual(second, third)
        from english_bot.topics import starter
        self.message.voice = None
        self.message.text = "A park is a good place for a break."
        chat = next(h for h in self.app.handlers[0] if isinstance(h, MessageHandler))
        await chat.callback(self.update, self.context)
        self.assertEqual(self.tutor.respond.call_args.args[0][-2]["content"], starter("daily", index=2))

    async def test_refresh_works_without_in_memory_panel_after_restart(self):
        await self.tap("refresh:nature:11")
        from english_bot.topics import starter
        self.assertIn(starter("nature", index=0), self.query.edit_message_text.call_args.args[0])

    async def test_feedback_mode_routes_answers_and_can_pause_and_resume(self):
        self.store.append_turn(1, "Yesterday I go to shop.", "What did you buy?")
        ordinary_history = self.store.history(1)
        await self.tap("feedback")
        self.assertTrue(self.store.feedback_session(1)["active"])
        self.assertTrue(self.tutor.respond.call_args.kwargs["feedback"])
        self.message.voice = None
        self.message.text = "Yesterday I went to the shop."
        chat = next(h for h in self.app.handlers[0] if isinstance(h, MessageHandler))
        await chat.callback(self.update, self.context)
        self.tutor.coach.assert_awaited_once()
        self.assertEqual(self.tutor.coach.call_args.args[1], self.message.text)
        self.assertEqual(self.store.history(1), ordinary_history)
        self.assertEqual(len(self.store.feedback_session(1)["history"]), 2)
        await self.tap("feedback:exit")
        self.assertFalse(self.store.feedback_session(1)["active"])
        await chat.callback(self.update, self.context)
        self.assertEqual(self.tutor.coach.await_count, 1)
        calls = self.tutor.respond.await_count
        await self.tap("feedback")
        self.assertTrue(self.store.feedback_session(1)["active"])
        self.assertEqual(self.tutor.respond.await_count, calls)
        self.assertIn("Good work", self.message.reply_text.call_args.args[0])

    async def test_feedback_buttons_continue_the_current_lesson(self):
        await self.tap("feedback")
        for action in ("explain", "example", "practice"):
            await self.tap("feedback:" + action)
            self.assertEqual(self.tutor.coach.call_args.args[1], "[Lesson action: " + action + "]")
        self.assertEqual(len(self.store.feedback_session(1)["history"]), 6)

    async def test_failed_new_review_preserves_the_saved_lesson(self):
        self.store.start_feedback(1, [], "Saved lesson")
        self.store.append_turn(1, "I has an idea.", "Tell me more.")
        self.tutor.respond.side_effect = RuntimeError()
        with self.assertRaises(RuntimeError):
            await self.tap("feedback:new")
        self.assertEqual(self.store.feedback_session(1)["review"], "Saved lesson")

    async def test_choosing_topic_leaves_feedback_mode(self):
        await self.tap("feedback")
        await self.tap("topic:science")
        self.assertFalse(self.store.feedback_session(1)["active"])

    async def test_voice_answers_are_transcribed_and_sent_to_the_lesson(self):
        await self.tap("feedback")
        self.tutor.transcribe = AsyncMock(return_value="Yesterday I went to the shop.")
        file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"ogg")))
        self.message.voice = SimpleNamespace(duration=2, file_size=3, get_file=AsyncMock(return_value=file))
        chat = next(h for h in self.app.handlers[0] if isinstance(h, MessageHandler))
        await chat.callback(self.update, self.context)
        self.assertEqual(self.tutor.coach.call_args.args[1], "Yesterday I went to the shop.")
        self.assertEqual(self.store.history(1), [])

    async def test_chat_command_exits_and_reset_deletes_the_lesson(self):
        await self.tap("feedback")
        command = next(h for h in self.app.handlers[0] if isinstance(h, CommandHandler))
        self.message.text = "/chat"
        await command.callback(self.update, self.context)
        self.assertFalse(self.store.feedback_session(1)["active"])
        self.message.text = "/feedback"
        await command.callback(self.update, self.context)
        self.assertTrue(self.store.feedback_session(1)["active"])
        self.message.text = "/reset"
        await command.callback(self.update, self.context)
        self.assertIsNone(self.store.feedback_session(1))

    async def test_practice_clock_only_changes_for_authored_learning_turns(self):
        await self.tap("feedback")
        self.assertIsNone(self.store.reminder_state(1)["last_practiced"])
        await self.tap("feedback:example")
        self.assertIsNone(self.store.reminder_state(1)["last_practiced"])
        chat = next(h for h in self.app.handlers[0] if isinstance(h, MessageHandler))
        self.message.voice = None
        self.message.text = "I went to the museum yesterday."
        await chat.callback(self.update, self.context)
        recorded = self.store.reminder_state(1)["last_practiced"]
        self.assertIsNotNone(recorded)
        await self.tap("feedback:explain")
        self.assertEqual(self.store.reminder_state(1)["last_practiced"], recorded)
        self.message.text = "Thanks!"
        await chat.callback(self.update, self.context)
        self.assertEqual(self.store.reminder_state(1)["last_practiced"], recorded)

    async def test_reminder_controls_are_opt_in_and_preview_does_not_send(self):
        await self.tap("reminder:menu")
        self.assertFalse(self.store.reminder_state(1)["enabled"])
        await self.tap("reminder:preview")
        self.assertIn("Reminder preview", self.query.edit_message_text.call_args.args[0])
        self.assertEqual(self.store.recent_reminders(1, 0), [])
        await self.tap("reminder:on")
        self.assertTrue(self.store.reminder_state(1)["enabled"])
        await self.tap("reminder:time:18:00")
        await self.tap("reminder:zone:Europe/London")
        state = self.store.reminder_state(1)
        self.assertEqual((state["preferred_time"], state["timezone"]), ("18:00", "Europe/London"))
        await self.tap("reminder:off")
        self.assertFalse(self.store.reminder_state(1)["enabled"])

    async def test_reminder_practice_button_resumes_lesson_without_faking_practice(self):
        self.store.start_feedback(1, [], "Existing exercise")
        self.store.set_feedback_active(1, False)
        await self.tap("reminder:practice")
        self.assertTrue(self.store.feedback_session(1)["active"])
        self.assertIsNone(self.store.reminder_state(1)["last_practiced"])
        self.assertIn("Existing exercise", self.message.reply_text.call_args.args[0])

    async def test_reminder_command_validates_custom_time(self):
        command = next(h for h in self.app.handlers[0] if isinstance(h, CommandHandler))
        self.message.text = "/reminders"
        self.context.args = ["time", "23:00"]
        await command.callback(self.update, self.context)
        self.assertEqual(self.store.reminder_state(1)["preferred_time"], "19:00")
        self.assertIn("09:00", self.message.reply_text.call_args.args[0])
