import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_key: str
    chat_model: str
    transcribe_model: str
    tts_model: str
    tts_voice: str
    database_path: str
    allowed_users: frozenset[int]

    @classmethod
    def load(cls):
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not token or not key:
            raise ValueError("Set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY in .env first.")
        return cls(
            token, key,
            os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
            os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe"),
            os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            os.getenv("OPENAI_TTS_VOICE", "coral"),
            os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            frozenset(int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()),
        )
