# English Telegram Tutor

A Python bot that turns Telegram voice messages into text, chats with learners,
asks follow-up questions, and reviews recent English mistakes. Optional replies
arrive as playable Telegram voice notes, alongside text. Works in private chats.

## Setup (Windows PowerShell)

Install Python 3.11 or newer, then open PowerShell in this folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Edit `.env` and fill in:

- `TELEGRAM_BOT_TOKEN`: create a bot through Telegram's official `@BotFather`
  using `/newbot`, then copy its token.
- `OPENAI_API_KEY`: your OpenAI API key. The bot uses your API account;
  a ChatGPT subscription alone does not configure API access or billing.

Never commit or share `.env`. For a personal bot, put your numeric Telegram user
ID in `ALLOWED_USER_IDS`; leave empty if anyone should be able to use it.
Requests from allowed learners consume the operator's API quota.

Start the bot:

```powershell
.venv\Scripts\python.exe -m english_bot
```

Open your bot in Telegram and send `/start`. Keep this process running to receive
messages; stop with Ctrl+C. Long polling needs no public server or webhook.
Run only one polling instance per Telegram token and database.

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` instead.

## Practice commands

| Command | Result |
| --- | --- |
| `/start`, `/help` | Help and an opening conversation question |
| `/voice on` | AI-generated spoken replies plus text |
| `/voice off` | Text replies (default) |
| `/level A2` | Set difficulty: A1, A2, B1, B2, C1, C2; default B1 |
| `/feedback` | Examples, corrections, explanations, and a practice exercise |
| `/reset` | Delete your local conversation and preferences |
| `/privacy` | Explain storage and external processing |

Send voice notes of up to three minutes / 19 MB, or ordinary text messages.
The bot shows what it transcribed, then responds conversationally. Feedback uses
the latest ten exchanges. Speech delivery failure falls back to the text reply.
Feedback cannot assess pronunciation from text, and transcription can introduce
mistakes. Voice notes go directly to the transcription API as OGG; no FFmpeg
installation is required.

## Configuration and data

Model names and TTS voice can be changed in `.env` to match your API account's
available models. Defaults: `gpt-4.1-mini` for conversation, `gpt-transcribe` for
transcription, and `gpt-4o-mini-tts` / `coral` for spoken output.

SQLite stores the latest ten exchanges per learner plus voice/level preferences
in `data/bot.sqlite3`. Learners are isolated by Telegram user ID. Audio is held
temporarily in memory. Transcription and conversation are sent to OpenAI;
Responses requests use `store=False`, which is not a claim of zero provider
retention. `/reset` removes local user records but cannot delete provider records
or existing backups. Secure the data directory if hosting for other learners.

The initial implementation processes updates sequentially to keep turns ordered.
It suits a personal bot or small practice group; busy deployments need per-user
queues, rate limits, and a multi-worker storage design.

## Validation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q src tests
```

Tests exercise history bounds, isolation, persistence, and reset without API calls.
For a live check: send a voice note, answer the follow-up, request `/feedback`,
enable `/voice on`, send another message, then `/reset`. Confirm the audio plays
and `/feedback` asks for new messages after reset.

If requests fail, verify both tokens, API billing, model access, and connectivity.
If only audio fails, use `/voice off` while checking the TTS model/voice settings.

API references: [text generation](https://developers.openai.com/api/docs/guides/text),
[transcription](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create),
[speech output](https://developers.openai.com/api/reference/python/resources/audio/subresources/speech/methods/create).
