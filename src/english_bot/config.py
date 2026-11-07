import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    gemini_key: str
    chat_model: str
    transcribe_model: str
    database_path: str
    allowed_users: frozenset[int]
    piper_model_path: str = "models/en_US-ljspeech-medium.onnx"
    piper_speed: float = 1.0
    piper_threads: int = 2

    @classmethod
    def load(cls):
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not token or not key:
            raise ValueError("Set TELEGRAM_BOT_TOKEN and GEMINI_API_KEY in .env first.")
        speed = float(os.getenv("PIPER_SPEED", "1.0"))
        threads = int(os.getenv("PIPER_THREADS", "2"))
        if not 0.5 <= speed <= 2.0 or not 1 <= threads <= 16:
            raise ValueError("PIPER_SPEED must be 0.5-2.0 and PIPER_THREADS must be 1-16.")
        return cls(
            token, key,
            os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite"),
            os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-flash-lite"),
            os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            frozenset(int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()),
            os.getenv("PIPER_MODEL_PATH", "models/en_US-ljspeech-medium.onnx"),
            speed,
            threads,
        )
