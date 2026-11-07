import unittest
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from telegram.error import Forbidden

from english_bot.reminders import (
    DAY, ReminderService, elapsed_label, local_time, next_regular,
    reminder_message, tomorrow, validate_time, validate_zone,
)
from english_bot.store import Store


def stamp(value, zone="Europe/Kyiv"):
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(zone)).timestamp()


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.now = stamp("2026-10-26T12:00")
        self.service = ReminderService(self.store, frozenset({7}), clock=lambda: self.now)
        self.service.touch(7, 7)
        self.store.start_feedback(7, [{"role": "user", "content": "I has a plan."}], "A saved lesson")
        self.bot = AsyncMock()

    def tearDown(self):
        self.store.close()

    def enable_and_go_due(self):
        self.service.configure(7, enabled=True)
        self.now = self.store.reminder_state(7)["next_due"]

    async def test_default_off_and_no_fake_practice_time(self):
        self.now = stamp("2026-10-27T19:00")
        await self.service.tick(self.bot)
        self.bot.send_message.assert_not_awaited()
        self.assertFalse(self.store.reminder_state(7)["enabled"])
        self.assertIsNone(self.store.reminder_state(7)["last_practiced"])
        self.assertNotIn("Last practice:", reminder_message(self.store.reminder_state(7), self.now))

    async def test_silent_message_has_real_elapsed_time_and_cannot_repeat(self):
        self.enable_and_go_due()
        self.store.record_practice(7, now=self.now - 2 * DAY - 4 * 3600)
        await self.service.tick(self.bot)
        args = self.bot.send_message.call_args.kwargs
        self.assertTrue(args["disable_notification"])
        self.assertIn("2 days, 4 hours ago", args["text"])
        self.assertEqual(args["reply_markup"].inline_keyboard[0][0].callback_data, "ui:reminder:practice")
        await self.service.tick(self.bot)
        restarted = ReminderService(self.store, clock=lambda: self.now)
        await restarted.tick(self.bot)
        self.assertEqual(self.bot.send_message.await_count, 1)

    async def test_skip_practice_today_active_chat_and_empty_material(self):
        self.enable_and_go_due()
        self.store.record_practice(7, now=self.now - 3600)
        await self.service.tick(self.bot)
        self.bot.send_message.assert_not_awaited()
        self.store.update_reminders(7, last_practiced=None, next_due=self.now, last_seen=self.now - 60)
        await self.service.tick(self.bot)
        self.bot.send_message.assert_not_awaited()
        self.store.start_feedback(7, [], "Intro only")
        self.store.update_reminders(7, next_due=self.now, last_seen=self.now - 3600)
        await self.service.tick(self.bot)
        self.bot.send_message.assert_not_awaited()

    async def test_two_unanswered_pause_until_interaction_but_manual_off_stays_off(self):
        self.enable_and_go_due()
        await self.service.tick(self.bot)
        self.now = self.store.reminder_state(7)["next_due"]
        await self.service.tick(self.bot)
        state = self.store.reminder_state(7)
        self.assertFalse(state["enabled"])
        self.assertTrue(state["auto_paused"])
        self.assertEqual(state["unanswered"], 2)
        self.service.touch(7, 7)
        self.assertTrue(self.store.reminder_state(7)["enabled"])
        self.assertEqual(self.store.reminder_state(7)["unanswered"], 0)
        self.service.configure(7, enabled=False)
        self.service.touch(7, 7)
        self.assertFalse(self.store.reminder_state(7)["enabled"])

    async def test_daily_and_weekly_caps_include_contextual_nudges(self):
        self.enable_and_go_due()
        await self.service.tick(self.bot)
        self.now += 3600
        self.service.touch(7, 7)
        self.store.update_reminders(7, new_messages=12)
        await self.service.maybe_nudge(self.bot, 7, "Thanks!")
        self.assertEqual(self.bot.send_message.await_count, 1)
        self.service.snooze(7)
        self.now = self.store.reminder_state(7)["next_due"]
        await self.service.tick(self.bot)
        self.assertEqual(self.bot.send_message.await_count, 2)
        self.now += DAY
        self.service.touch(7, 7)
        await self.service.maybe_nudge(self.bot, 7, "That's all for today.")
        self.assertEqual(self.bot.send_message.await_count, 2)

    async def test_contextual_invitation_only_at_a_natural_closing(self):
        self.enable_and_go_due()
        self.service.touch(7, 7)
        self.store.update_reminders(7, new_messages=10)
        await self.service.maybe_nudge(self.bot, 7, "Thanks, can you explain this further?")
        self.bot.send_message.assert_not_awaited()
        await self.service.maybe_nudge(self.bot, 7, "Thank you for your help!")
        self.bot.send_message.assert_awaited_once()
        await self.service.tick(self.bot)
        self.assertEqual(self.bot.send_message.await_count, 1)

    async def test_no_catchup_burst_after_downtime(self):
        self.enable_and_go_due()
        self.now += 2 * DAY
        await self.service.tick(self.bot)
        self.bot.send_message.assert_not_awaited()
        self.assertGreater(self.store.reminder_state(7)["next_due"], self.now)

    async def test_failed_send_is_not_retried_or_replayed(self):
        self.enable_and_go_due()
        self.bot.send_message.side_effect = RuntimeError("Network timeout")
        with self.assertLogs("english_bot.reminders", level="WARNING"):
            await self.service.tick(self.bot)
        await self.service.tick(self.bot)
        self.assertEqual(self.bot.send_message.await_count, 1)
        self.assertEqual(self.store.reminder_state(7)["unanswered"], 0)

    async def test_blocked_bot_is_paused_and_allowlist_is_respected(self):
        self.enable_and_go_due()
        denied = ReminderService(self.store, frozenset({8}), clock=lambda: self.now)
        await denied.tick(self.bot)
        self.bot.send_message.assert_not_awaited()
        self.store.update_reminders(7, next_due=self.now)
        self.bot.send_message.side_effect = Forbidden("Blocked")
        await self.service.tick(self.bot)
        self.assertFalse(self.store.reminder_state(7)["enabled"])
        self.assertFalse(self.store.reminder_state(7)["auto_paused"])


class ReminderTimeTests(unittest.TestCase):
    def test_timezone_schedule_follows_dst_and_local_weekdays(self):
        after_friday = stamp("2026-03-27T20:00")
        due = next_regular(after_friday, "Europe/Kyiv", "19:00")
        local = local_time(due, "Europe/Kyiv")
        self.assertEqual((local.weekday(), local.hour, local.minute), (1, 19, 0))
        self.assertEqual(local.utcoffset().total_seconds(), 3 * 3600)
        before_dst = stamp("2026-03-28T19:00")
        self.assertEqual(tomorrow(before_dst, "Europe/Kyiv", "19:00") - before_dst, 23 * 3600)

    def test_elapsed_time_and_validation(self):
        self.assertEqual(elapsed_label(None, now=100), "No practice recorded yet")
        self.assertEqual(elapsed_label(0, now=60), "1 minute ago")
        self.assertEqual(elapsed_label(0, now=2 * DAY + 3600), "2 days, 1 hour ago")
        for value in ("23:00", "7:00", "19:99", "bad"):
            with self.assertRaises(ValueError):
                validate_time(value)
        with self.assertRaises(ValueError):
            validate_zone("Not/AZone")
        validate_time("18:30")
        validate_zone("Europe/Kyiv")
