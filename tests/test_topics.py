import unittest

from english_bot.topics import ROTATION_SECONDS, TOPICS, starter, topic_screen
from english_bot.ui import topics_screen


class TopicTests(unittest.TestCase):
    def test_all_six_topics_change_at_the_boundary_and_stay_stable_within_it(self):
        self.assertEqual(len(TOPICS), 6)
        self.assertEqual(ROTATION_SECONDS, 1800)
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(starter(topic, 0), starter(topic, 1799.99))
                self.assertNotEqual(starter(topic, 1799.99), starter(topic, 1800))
                self.assertEqual(starter(topic, 1800), starter(topic, 3599.99))
                questions = TOPICS[topic][1]
                self.assertEqual(len(questions), len(set(questions)))
                self.assertTrue(all(q.endswith("?") for q in questions))

    def test_topic_buttons_and_safe_question_screen(self):
        _, markup = topics_screen()
        targets = {b.callback_data for row in markup.inline_keyboard for b in row}
        self.assertTrue({"ui:topic:" + key for key in TOPICS}.issubset(targets))
        text, markup = topic_screen("history", now=0)
        self.assertIn("History &amp; society", text)
        self.assertIn(starter("history", 0), text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "ui:refresh:history:0")
