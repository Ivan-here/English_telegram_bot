import tempfile
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


if __name__ == "__main__":
    unittest.main()
