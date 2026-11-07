"""Offline Piper CPU synthesis and Telegram-compatible MP3 encoding."""

import json
import threading
from pathlib import Path

import lameenc
import numpy as np

from .config import Settings


class PiperSpeech:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine = None
        self._syn_config = None
        self._lock = threading.Lock()

    def _load_engine(self):
        # Optional dependency: ordinary chat and unit tests need no ONNX runtime.
        import onnxruntime as ort
        from piper import PiperVoice, SynthesisConfig
        from piper.config import PiperConfig

        model_path = self.settings.piper_model_path
        for path in (model_path, model_path + ".json"):
            if not Path(path).is_file():
                raise RuntimeError("Piper model files are missing. Run scripts/download_piper.py first.")
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.settings.piper_threads
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            model_path, sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        config = PiperConfig.from_dict(json.loads(Path(model_path + ".json").read_text(encoding="utf-8")))
        self._syn_config = SynthesisConfig(length_scale=config.length_scale / self.settings.piper_speed)
        return PiperVoice(session=session, config=config)

    def synthesise(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            raise ValueError("Cannot speak empty text")
        if len(text) > 12000:
            raise ValueError("Speech text is too long")
        with self._lock:
            if self._engine is None:
                self._engine = self._load_engine()
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(64)
            rate = self._engine.config.sample_rate
            encoder.set_in_sample_rate(rate)
            encoder.set_channels(1)
            encoder.set_quality(2)
            output = bytearray()
            count = 0
            # Piper yields sentence-sized chunks, encoded without temporary WAV files.
            for chunk in self._engine.synthesize(text, syn_config=self._syn_config):
                if chunk.sample_rate != rate or chunk.sample_channels != 1 or chunk.sample_width != 2:
                    raise ValueError("Unexpected Piper audio format")
                samples = np.asarray(chunk.audio_float_array, dtype=np.float32)
                if samples.size == 0 or not np.isfinite(samples).all():
                    raise ValueError("Piper returned invalid audio")
                pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
                output.extend(encoder.encode(pcm))
                output.extend(encoder.encode(b"\0\0" * int(rate * 0.15)))
                count += 1
            if not count:
                raise ValueError("Piper returned no audio")
            output.extend(encoder.flush())
            return bytes(output)
