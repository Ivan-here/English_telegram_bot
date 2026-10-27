import logging
from io import BytesIO

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings
from .store import Store
from .tutor import Tutor

LOG = logging.getLogger(__name__)
HELP = """Hi! Send a voice message or type something in English and let's chat.
I will ask follow-up questions to help you practise.

/feedback — review mistakes in your recent messages
/voice on — receive AI-generated spoken replies plus text
/voice off — text replies only (default)
/level A1|A2|B1|B2|C1|C2 — choose difficulty (default B1)
/reset — delete saved conversation and preferences
/privacy — how your messages are handled
/help — show this help

What did you do today?"""
PRIVACY = (
    "Your messages and voice recordings are sent to OpenAI to generate responses. "
    "The latest ten conversation exchanges and your settings are saved locally by the bot operator. "
    "Voice recordings are held in memory during processing, not saved by this bot. "
    "Use /reset to erase your local conversation and settings; this does not delete provider records. "
    "Spoken replies use an AI-generated voice."
)


async def send_text(message, text):
    for start in range(0, len(text), 4000):
        await message.reply_text(text[start:start + 4000])


def create_application(settings: Settings):
    store = Store(settings.database_path)
    tutor = Tutor(settings)

    async def allowed(update):
        if not update.effective_message or not update.effective_user:
            return False
        if update.effective_chat.type != ChatType.PRIVATE:
            return False
        if settings.allowed_users and update.effective_user.id not in settings.allowed_users:
            await update.effective_message.reply_text("This bot is currently limited to approved learners.")
            return False
        return True

    async def command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await allowed(update):
            return
        message = update.effective_message
        uid = update.effective_user.id
        name = message.text.split()[0].split("@")[0].lower()
        voice, level = store.preferences(uid)
        if name in ("/start", "/help"):
            await message.reply_text(HELP)
            if name == "/start":
                await message.reply_text(PRIVACY)
        elif name == "/privacy":
            await message.reply_text(PRIVACY)
        elif name == "/reset":
            store.reset(uid)
            await message.reply_text("Your saved conversation and settings have been deleted. Let's start fresh!")
        elif name == "/voice":
            value = context.args[0].lower() if len(context.args) == 1 else ""
            if value not in ("on", "off"):
                await message.reply_text(f"Voice replies are {'on' if voice else 'off'}. Use /voice on or /voice off.")
                return
            store.set_preferences(uid, value == "on", level)
            await message.reply_text("AI-generated voice replies enabled." if value == "on" else "Text replies enabled.")
        elif name == "/level":
            value = context.args[0].upper() if len(context.args) == 1 else ""
            if value not in ("A1", "A2", "B1", "B2", "C1", "C2"):
                await message.reply_text(f"Current level: {level}. Use /level A1, A2, B1, B2, C1, or C2.")
                return
            store.set_preferences(uid, voice, value)
            await message.reply_text(f"Practice level set to {value}.")
        elif name == "/feedback":
            history = store.history(uid)
            if not history:
                await message.reply_text("Send a few voice or text messages first, then ask for /feedback.")
                return
            await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
            reply = await tutor.respond(history, level, feedback=True)
            await deliver(message, reply, voice)

    async def deliver(message, reply, voice):
        await send_text(message, reply)
        if voice:
            try:
                audio = BytesIO(await tutor.speech(reply))
                audio.name = "reply.ogg"
                await message.reply_voice(voice=audio, caption="AI-generated voice")
            except Exception as error:
                LOG.warning("Voice output failed (%s)", type(error).__name__)
                await message.reply_text("I couldn't send a voice reply this time. You can read my response above.")

    async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await allowed(update):
            return
        message = update.effective_message
        uid = update.effective_user.id
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
        if message.voice:
            # Leave room below both Telegram download and OpenAI upload limits.
            if message.voice.duration > 180 or (message.voice.file_size or 0) > 19_000_000:
                await message.reply_text("Please send a voice message under 3 minutes and 19 MB.")
                return
            file = await message.voice.get_file()
            audio = await file.download_as_bytearray()
            if len(audio) > 19_000_000:
                await message.reply_text("That recording is too large. Please send a shorter one.")
                return
            text = await tutor.transcribe(bytes(audio))
            if not text:
                await message.reply_text("I couldn't hear any words. Please try another recording.")
                return
            if len(text) > 6000:
                await message.reply_text("Please send a shorter recording so we can practise one idea at a time.")
                return
            await send_text(message, "I heard: " + text)
        else:
            text = (message.text or "").strip()
            if not text:
                return
            if len(text) > 6000:
                await message.reply_text("Please keep each message under 6,000 characters.")
                return
        voice, level = store.preferences(uid)
        history = store.history(uid) + [{"role": "user", "content": text}]
        reply = await tutor.respond(history, level)
        await send_text(message, reply)
        store.append_turn(uid, text, reply)
        if voice:
            # The text has already been delivered and saved; speech is optional.
            try:
                audio = BytesIO(await tutor.speech(reply))
                audio.name = "reply.ogg"
                await message.reply_voice(voice=audio, caption="AI-generated voice")
            except Exception as error:
                LOG.warning("Voice output failed (%s)", type(error).__name__)
                await message.reply_text("Voice output is unavailable right now; my text reply is above.")

    async def on_error(update, context):
        # Avoid logging exception strings, which can contain tokens or message content.
        LOG.error("Request failed (%s)", type(context.error).__name__)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "I couldn't complete that request. Please try again shortly. "
                    "If it keeps happening, ask the bot owner to check API access and billing."
                )
            except Exception:
                LOG.error("Could not send error notice")

    async def startup(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Start practising English"),
            BotCommand("feedback", "Review recent mistakes"),
            BotCommand("voice", "Turn spoken replies on or off"),
            BotCommand("level", "Set your English level"),
            BotCommand("reset", "Delete saved conversation and settings"),
            BotCommand("privacy", "Message and audio privacy"),
            BotCommand("help", "Show help"),
        ])

    async def shutdown(app):
        await tutor.client.close()
        store.close()

    # Sequential processing preserves turn order and avoids SQLite/thread races.
    app = (Application.builder().token(settings.telegram_token)
           .concurrent_updates(False).post_init(startup).post_shutdown(shutdown).build())
    app.add_handler(CommandHandler(["start", "help", "privacy", "reset", "voice", "level", "feedback"], command))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.VOICE | (filters.TEXT & ~filters.COMMAND)), chat))
    app.add_error_handler(on_error)
    return app


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = Settings.load()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    create_application(settings).run_polling(allowed_updates=["message"])
