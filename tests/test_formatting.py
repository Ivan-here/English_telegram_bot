import unittest

from english_bot.formatting import feedback_html, text_chunks


class FeedbackFormattingTests(unittest.TestCase):
    def test_points_labels_and_spacing(self):
        rendered = feedback_html("1. Past tense\nOriginal: I go yesterday.\nCorrection: I went yesterday.\nExplanation: Use the past tense.\nPractice\nDescribe yesterday.")
        self.assertIn("<b>1. Past tense</b>", rendered)
        self.assertIn("<b>Original:</b> I go yesterday.", rendered)
        self.assertIn("<b>Correction:</b> I went yesterday.", rendered)
        self.assertIn("<b>Explanation:</b> Use the past tense.", rendered)
        self.assertIn("\n\n<b>Practice</b>\n", rendered)

    def test_model_markdown_labels_are_rendered_without_stars(self):
        rendered = feedback_html("**1. Past tense**\n**Original:** I go.\n**Correction**: I went.\n__Explanation:__ Past tense.")
        self.assertNotIn("**", rendered)
        self.assertNotIn("__", rendered)
        self.assertIn("<b>Original:</b> I go.", rendered)

    def test_learner_text_cannot_inject_html(self):
        rendered = feedback_html('Original: <b>hello</b> & goodbye\n1. Use < instead of >')
        self.assertIn('&lt;b&gt;hello&lt;/b&gt; &amp; goodbye', rendered)
        self.assertIn('<b>1. Use &lt; instead of &gt;</b>', rendered)

    def test_advanced_lesson_labels_are_bold(self):
        rendered = feedback_html("Your focus\nPattern: Subject + verb\nExample: I agree.\nHint: Check the subject.\nProgress\nWell done.")
        for label in ["Your focus", "Pattern:", "Example:", "Hint:", "Progress"]:
            self.assertIn("<b>" + label + "</b>", rendered)

    def test_long_lessons_split_at_paragraph_boundaries_without_losing_content(self):
        paragraphs = [str(number) + ". " + "Example sentence. " * 20 for number in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = list(text_chunks(text))
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertEqual(" ".join(text.split()), " ".join(" ".join(chunks).split()))
