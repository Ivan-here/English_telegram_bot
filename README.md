# English Telegram Tutor (Gemini + local Piper)

A personal English practice bot for Telegram private chats. It transcribes voice
messages, chats in English, reviews mistakes, and optionally sends spoken replies.
Uses Google Gemini for chat/transcription and local Piper for spoken replies.
No OpenAI account or key is needed. Local speech has no API quota or per-request fee.

The learner chooses the topic. Everyday chat gets brief replies; requests for
history, reforms, science, or other explanations get fuller answers, usually
120-180 words (roughly 1 minute to 1 minute 20 seconds spoken, depending on pace).
Ask for a shorter answer or a different focus at any time. Follow-up questions
are optional. The bot has no live web browsing for current facts.

## Get your credentials

1. In Telegram, open the official @BotFather, send `/newbot`, follow the prompts,
   and copy the bot token. If you already have a bot token, reuse it.
2. Open https://aistudio.google.com/apikey, sign in, and create a Gemini API key
   in a Free-tier project. Keep billing disabled if you want no API charges.
   Check model availability and your actual quotas in AI Studio. Free does not
   mean unlimited; a paid Google subscription is not required for this API tier.
3. Edit `.env` in this folder (a blank template is supplied; otherwise copy
   `.env.example`). Fill TELEGRAM_BOT_TOKEN and GEMINI_API_KEY. Keep keys private.

```dotenv
TELEGRAM_BOT_TOKEN=your_botfather_token
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
GEMINI_TRANSCRIBE_MODEL=gemini-3.5-flash-lite
PIPER_SPEED=1.0
PIPER_THREADS=2
DATABASE_PATH=data/bot.sqlite3
ALLOWED_USER_IDS=
```

Leave ALLOWED_USER_IDS empty for the initial setup. After starting the bot, each
of you should send `/whoami` in your private chat with it. Add both returned
numeric IDs, separated by a comma, then restart the bot:

```dotenv
ALLOWED_USER_IDS=123456789,987654321
```

`/whoami` works even for users outside the allowlist and only returns their own ID.
An empty allowlist allows everyone to use the bot and consume its quota.

## Install and start (Windows PowerShell, Python 3.11–3.13 for local speech)

Run from this folder:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[speech]"
.venv\Scripts\python.exe scripts/download_piper.py
.venv\Scripts\python.exe -m english_bot
```

If the environment and dependencies are already installed, only the last command
is needed. Keep the process running; stop with Ctrl+C. No public server or webhook
is required. Run one polling instance per Telegram token/database.
Piper runs on CPU with two inference threads by default. The first spoken reply
loads the model; subsequent replies reuse it. The LAME encoder produces MP3 voice
replies without FFmpeg. Windows needs the Microsoft Visual C++ x64 runtime for
ONNX Runtime; the Docker image installs it automatically. Local speech requires
Python 3.11–3.13; the Docker image uses Python 3.11.

## Commands

`/start` opens a compact home screen with buttons for topic suggestions, feedback,
settings, and help. Settings use inline toggles and a six-level picker; screens
update in place. Topic suggestions are optional and do not limit what you can ask.
All existing slash commands remain available. `/topics` opens suggestions directly.
The transcript stays off by default, and `/start` sends one message.

Six topic categories offer 72 neutral conversation starters, including Work &
learning and Nature & environment. Questions rotate automatically every 30 minutes
at the hour and half-hour. Refresh question immediately advances to a different
question without waiting for the timer. An open, unanswered topic screen refreshes in place while the bot
is running; after a bot restart, reopen the topic or tap Refresh question.
Rotation uses a local question bank, so it makes no Gemini calls. Once you answer,
the question stops refreshing and is saved as context for your reply.

The interface follows Telegram's guidance for short welcome messages, inline
settings/navigation, and readable native formatting:
https://core.telegram.org/bots/guidelines and
https://core.telegram.org/bots/features#inline-keyboards.

| Command | Result |
| --- | --- |
| `/start`, `/help` | Help and an opening question |
| `/whoami` | Your numeric Telegram user ID |
| `/voice on`, `/voice off` | Enable/disable spoken replies (off by default) |
| `/settings` | View your settings |
| `/reminders` | Opt in to quiet practice invitations; choose time/timezone and preview |
| `/transcript on`, `/transcript off` | Show/hide the "I heard" transcript (off by default) |
| `/level A2` | Choose A1, A2, B1, B2, C1, C2 (default B1) |
| `/feedback` | Enter or resume guided feedback practice |
| `/chat` | Pause the lesson and return to ordinary conversation |
| `/reset` | Delete local conversation and preferences |
| `/privacy` | Explain storage and external processing |

Send text or voice notes up to 3 minutes / 10 MB. The transcript is hidden by
default; enable it with `/transcript on`. This preference is saved per user.
Audio stays in memory. Speech is converted to MP3 for
Telegram; if local synthesis fails, the text reply remains.
When voice replies are enabled, text arrives immediately with a temporary
"Preparing your voice reply" notice and a refreshed Telegram recording indicator.
The notice disappears when the audio is sent, or becomes a clear failure notice
if generation or delivery fails. Longer waits get a "Still preparing" update.

## Free-tier usage

The configured Gemini chat/transcription models are listed with free tiers in Google's pricing at setup
time, but availability and quotas can change by account, project, model, and region.
There is no automatic paid fallback. Keep the Google project on the Free tier;
the code cannot prevent charges if you deliberately enable billing on its project.
A voice turn uses one transcription request and one conversation request; enabling
voice replies uses local CPU without another Gemini request. Starting a new feedback
review or generating a coaching turn uses a Gemini request. Resuming a saved lesson
simply shows its latest reply without generating a new one.
When Gemini returns HTTP 429, the bot asks you to try later. Check AI Studio for
quota reset details; short-term rate limits and daily limits differ.

## Privacy and storage

Messages and incoming voice recordings go to Google Gemini. Spoken replies are
generated locally with Piper; no external speech service receives reply text. Free-tier content may be used by Google
to improve products. Avoid sensitive recordings. SQLite stores the last ten
exchanges per user and their preferences in data/bot.sqlite3. Feedback sessions
also save a snapshot of the reviewed conversation, the initial review, the latest
twelve practice exchanges, and whether feedback mode is active. `/reset` deletes
local records, not provider records or backups. Transcription can introduce errors;
feedback cannot assess pronunciation from text. The bot handles updates sequentially
and is intended for a personal bot or small group.

## Validation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q src tests
```

Tests use mocked Gemini HTTP responses, including quota failures, transcript input,
history conversion, and actual local audio conversion. They do not consume API quota.
For a live check after adding keys: `/start`, send text, send a voice note,
`/feedback`, `/voice on`, send another message, then `/reset`.

Official references:
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/audio
- https://github.com/OHF-Voice/piper1-gpl
- https://huggingface.co/rhasspy/piper-voices
- https://aistudio.google.com/apikey

## Docker Compose on this Windows server

The root `D:\Project\docker-compose.yml` includes `englishbot`. Its image matches
this server's Windows Server Core ltsc2019 containers. The supplied network
override reuses the existing project_default network. Credentials are read at
runtime from this folder's `.env` and excluded from the image. SQLite lives in
the persistent `english_bot_data` volume. No incoming port or nginx route is needed.

From an administrator PowerShell in `D:\Project`:

```powershell
.\docker-compose.exe -f docker-compose.yml -f scripts/compose-existing-network.yml up -d --build --no-deps englishbot
.\docker-compose.exe -f docker-compose.yml -f scripts/compose-existing-network.yml logs --tail 30 englishbot
```

Stop any separately launched local instance before starting the container.
After editing `.env`, run `up -d --no-deps englishbot` again to recreate it.
The restart policy keeps it running across Docker restarts. Do not remove its
volume unless you intend to erase all stored conversations and preferences.

## Practice reminders and the practice clock

Settings → Practice reminders (or `/reminders`) shows time since the learner's
last successful, authored feedback-mode turn. Text answers, questions, and
transcribed voice replies count. Opening/resuming feedback, lesson navigation
buttons, and simple acknowledgements such as "Thanks" do not reset the clock.
Older conversations have no reliable timestamps to backfill, so tracking starts
with new practice replies. Timestamps and preferences persist across restarts.

Reminders are opt-in and off by default. The starting schedule is Tuesday and
Friday at 19:00 Europe/Kyiv. Buttons offer alternative times and timezones;
`/reminders time 18:30` and `/reminders timezone America/Chicago` support custom
values. Times are limited to 09:00–20:59 local time. IANA timezone data is bundled
for Windows and daylight-saving transitions are respected.

Invitations use short, playful emoji messages and a real elapsed-practice label.
They include Practise now (opens/resumes feedback), Tomorrow (snoozes to the next
local day at the chosen time), Pause reminders, and settings. The preview edits
the current screen without creating a delivery or enabling reminders. No Gemini
requests or speech generation are used to compose reminders.

All scheduled/contextual invitations share these rules:

- At most one per local day and two attempts in any rolling seven days.
- Only when a saved lesson has learner material or ten new chat messages exist.
- Skip days with practice and skip scheduled reminders during recent chat activity.
- A contextual invitation may appear after a short natural closing, such as
  "Thanks for your help", following ten new chat messages. It requires opt-in too.
- Delivery is silent (a notification can appear, but without sound).
- After two delivered reminders without a subsequent interaction, pause until
  the learner interacts with the bot again. Explicitly turning reminders off
  stays off. Snoozing still respects the shared daily/weekly limits.
- Discard schedule slots missed by more than an hour, instead of sending catch-up
  messages after downtime. Reserve attempts before network I/O to prevent replay
  after a restart. Failed/uncertain sends conservatively consume the cap and are
  not immediately retried. Blocked bots are paused.

`/reset` deletes practice timestamps, reminder consent/settings, and delivery
history alongside conversation and lesson data. The scheduler checks once a
minute, so a reminder may arrive slightly after the selected time.

## Guided feedback mode

Feedback mode reviews the learner's actual messages in depth: grammar, sentence
construction, word order, clauses, formulation, cohesion, word choice, and natural
phrasing. The initial review normally uses 400–650 words when the sample supports
it, with up to six prioritised examples. Every example includes original wording,
a correction, an explanation, a reusable pattern, and a fresh example. Optional
style improvements are distinguished from errors, and uncertain transcripts are
treated cautiously.

The review ends with one exercise. Subsequent text and voice replies go to the
lesson coach, which checks answers, explains underlying rules, offers hints and
examples, and progresses through the learner's priorities. The Explain further,
Another example, and Next exercise buttons also continue the current lesson.
With no prior conversation, the mode asks for a starting sentence or paragraph.

Back to chat, `/chat`, `/start`, or choosing a topic returns to ordinary chat;
`/feedback` resumes the saved lesson. Settings/help/privacy do not end it.
Review latest chat starts a fresh review of ordinary conversation. Lessons are
stored separately so exercises do not replace the conversational evidence being
reviewed. The initial examples and review remain available even after older
practice turns are pruned. The mode survives container restarts; `/reset` erases it.
Long lessons split at paragraph boundaries and use bold Telegram headings/labels.
Voice replies use the same Piper settings and visible generation indicator.

## Local speech model

The Docker build downloads the official en_US-ljspeech-medium Piper voice model
(about 64 MB), its ONNX configuration, and model card. Downloads are verified
against the official voice manifest. Piper is GPL-3.0-or-later; the selected voice's
model card documents its dataset and licensing. Package license files and the
model card remain in the image. Runtime speech needs no API key or network access.

PIPER_MODEL_PATH defaults to models/en_US-ljspeech-medium.onnx; the matching .json
configuration must sit alongside it. PIPER_SPEED accepts 0.5–2.0 (1.0 is normal).
PIPER_THREADS defaults to 2 to limit CPU use on this shared server. Model loading
is lazy and cached across replies. Synthesis uses sentence-sized chunks encoded
in memory as MP3, with no FFmpeg or temporary WAV files.

The Windows Docker build installs the Microsoft C++ runtime and runs an actual
offline speech test before replacing the live container. Gemini still handles
incoming voice transcription and conversation, with its own separate quotas.
The temporary preparation notice and recording indicator remain active while
speech is generated and uploaded.

Measured on this server with two inference threads: the same 150-word sample
took 4.51 seconds with Piper (59.5 seconds of valid MP3 audio), compared with
32.86 seconds using Kokoro. This is a warm-model measurement; the first short
reply in a fresh process took 8.66 seconds including model initialization.
Actual latency depends on reply length and server load.
