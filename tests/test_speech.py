import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import numpy as np

from english_bot.config import Settings
from english_bot.speech import PiperSpeech


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.speech = PiperSpeech(Settings("token", "key", "chat", "audio", ":memory:", frozenset()))
        self.engine = Mock()
        self.engine.config.sample_rate = 22050
        self.chunk = SimpleNamespace(sample_rate=22050, sample_channels=1, sample_width=2,
                                     audio_float_array=np.zeros(2205, dtype=np.float32))
        self.engine.synthesize.return_value = [self.chunk]

    def test_local_model_is_reused_and_complete_reply_is_encoded(self):
        with patch.object(self.speech, "_load_engine", return_value=self.engine) as load:
            result = self.speech.synthesise("First paragraph.\n\nSecond paragraph.")
            self.speech.synthesise("Another reply.")
            load.assert_called_once()
        self.assertEqual([call.args[0] for call in self.engine.synthesize.call_args_list],
                         ["First paragraph.\n\nSecond paragraph.", "Another reply."])
        self.assertEqual(result[0], 255)
        self.assertEqual(result[1] & 224, 224)
        self.assertGreater(len(result), 100)

    def test_nonfinite_audio_is_rejected(self):
        self.chunk.audio_float_array = np.array([float("nan")])
        with patch.object(self.speech, "_load_engine", return_value=self.engine):
            with self.assertRaises(ValueError):
                self.speech.synthesise("Hello")

    def test_empty_input_does_not_load_the_model(self):
        with patch.object(self.speech, "_load_engine") as load:
            with self.assertRaises(ValueError):
                self.speech.synthesise("   ")
            load.assert_not_called()
