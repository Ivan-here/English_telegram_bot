import tempfile
import sqlite3
import unittest
from pathlib import Path

from english_bot.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "bot.sqlite3")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_history_is_bounded_ordered_and_isolated(self):
        self.store.append_turn(2, "private", "secret")
        for number in range(15):
            self.store.append_turn(1, str(number), "reply")
        history = self.store.history(1)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], {"role": "user", "content": "5"})
        self.assertEqual(history[-2]["content"], "14")
        self.assertEqual(self.store.history(2)[0]["content"], "private")

    def test_persistence_and_reset_only_affect_one_user(self):
        self.store.append_turn(1, "hello", "hi")
        self.store.append_turn(2, "other", "hi")
        self.store.set_preferences(1, True, "A2")
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.preferences(1), (True, "A2"))
        self.assertEqual(len(self.store.history(1)), 2)
        self.store.reset(1)
        self.assertEqual(self.store.history(1), [])
        self.assertEqual(self.store.preferences(1), (False, "B1"))
        self.assertEqual(len(self.store.history(2)), 2)

    def test_transcript_is_off_by_default_and_independent_of_other_settings(self):
        self.assertFalse(self.store.show_transcript(1))
        self.store.set_show_transcript(1, True)
        self.store.set_preferences(1, True, "A2")
        self.assertTrue(self.store.show_transcript(1))
        self.assertFalse(self.store.show_transcript(2))
        self.store.close()
        self.store = Store(self.path)
        self.assertTrue(self.store.show_transcript(1))
        self.store.set_show_transcript(1, False)
        self.assertEqual(self.store.preferences(1), (True, "A2"))
        self.store.set_show_transcript(1, True)
        self.store.reset(1)
        self.assertFalse(self.store.show_transcript(1))

    def test_existing_database_migrates_without_losing_preferences(self):
        legacy_path = str(Path(self.temp.name) / "legacy.sqlite3")
        with sqlite3.connect(legacy_path) as db:
            db.execute("CREATE TABLE preferences (user_id INTEGER PRIMARY KEY, voice INTEGER NOT NULL DEFAULT 0, level TEXT NOT NULL DEFAULT 'B1')")
            db.execute("INSERT INTO preferences VALUES (1, 1, 'B2')")
        db.close()
        migrated = Store(legacy_path)
        try:
            self.assertEqual(migrated.preferences(1), (True, "B2"))
            self.assertFalse(migrated.show_transcript(1))
            migrated.set_show_transcript(1, True)
            self.assertEqual(migrated.preferences(1), (True, "B2"))
        finally:
            migrated.close()

    def test_starter_question_is_preserved_with_its_answer_and_bounded(self):
        for number in range(30):
            self.store.append_prompt(1, f"Question {number}?")
        self.assertEqual(len(self.store.history(1)), 20)
        self.store.append_turn(1, "My answer", "Thanks")
        self.assertEqual(len(self.store.history(1)), 20)
        self.assertEqual(self.store.history(1)[-3], {"role": "assistant", "content": "Question 29?"})
        self.assertEqual(self.store.history(2), [])

    def test_feedback_sessions_persist_are_isolated_and_reset(self):
        source = [{"role": "user", "content": "I has a plan."}]
        self.store.start_feedback(1, source, "Use I have.")
        self.store.append_feedback_turn(1, "I have a plan.", "Correct.")
        self.store.start_feedback(2, [], "Other lesson")
        self.store.set_feedback_active(1, False)
        self.store.close()
        self.store = Store(self.path)
        session = self.store.feedback_session(1)
        self.assertFalse(session["active"])
        self.assertEqual(session["source"], source)
        self.assertEqual(session["history"][-1]["content"], "Correct.")
        self.assertEqual(self.store.history(1), [])
        self.store.reset(1)
        self.assertIsNone(self.store.feedback_session(1))
        self.assertEqual(self.store.feedback_session(2)["review"], "Other lesson")

    def test_feedback_history_is_bounded_but_source_and_review_remain(self):
        self.store.start_feedback(1, [{"role": "user", "content": "Original"}], "Initial review")
        for number in range(20):
            self.store.append_feedback_turn(1, str(number), "Lesson reply")
        session = self.store.feedback_session(1)
        self.assertEqual(len(session["history"]), 24)
        self.assertEqual(session["history"][0]["content"], "8")
        self.assertEqual(session["review"], "Initial review")
        self.assertEqual(session["source"][0]["content"], "Original")

    def test_reminder_state_and_claim_survive_restart_and_reset(self):
        self.store.update_reminders(1, chat_id=1, enabled=1, next_due=100, timezone="Europe/Kyiv")
        self.store.record_practice(1, now=10)
        claim = self.store.claim_reminder(1, now=100, next_due=200, expected_due=100)
        self.assertIsNotNone(claim)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.reminder_state(1)["last_practiced"], 10)
        self.assertEqual(self.store.reminder_state(1)["next_due"], 200)
        self.assertIsNone(self.store.claim_reminder(1, now=100, next_due=200, expected_due=100))
        self.assertEqual(len(self.store.recent_reminders(1, 0)), 1)
        self.store.reset(1)
        self.assertFalse(self.store.reminder_state(1)["enabled"])
        self.assertIsNone(self.store.reminder_state(1)["last_practiced"])
        self.assertEqual(self.store.recent_reminders(1, 0), [])


if __name__ == "__main__":
    unittest.main()
