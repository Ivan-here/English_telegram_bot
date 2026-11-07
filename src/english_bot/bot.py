import logging
import asyncio
import time
from contextlib import suppress
from html import escape

from telegram import BotCommand, MenuButtonCommands, Update
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest, InvalidToken
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings
from . import ui
from . import topics
from .formatting import feedback_html, text_chunks
from .store import Store
from .tutor import QuotaExceeded, Tutor
from .voice_delivery import send_voice_reply
from .reminders import ReminderService, reminder_screen, reminder_message, reminder_keyboard, is_practice_reply

LOG = logging.getLogger(__name__)
async def send_text(message, text, feedback=False):
    chunks = list(text_chunks(text))
    for index, chunk in enumerate(chunks):
        if feedback:
            await message.reply_text(
                "📝 <b>Feedback mode · Learn &amp; practise</b>\n\n" + feedback_html(chunk),
                parse_mode="HTML",
                reply_markup=ui.feedback_keyboard() if index == len(chunks) - 1 else None,
            )
        else:
            await message.reply_text(chunk)


def create_application(settings: Settings):
    store = Store(settings.database_path)
    tutor = Tutor(settings)
    reminders = ReminderService(store, settings.allowed_users)
    topic_panels = {}
    pending_questions = {}
    panel_lock = asyncio.Lock()
    refresh_task = None
    reminder_task = None

    def clear_topics(uid):
        for key, panel in list(topic_panels.items()):
            if panel[0] == uid:
                topic_panels.pop(key, None)

    async def refresh_topics(app):
        while True:
            await asyncio.sleep(topics.ROTATION_SECONDS - time.time() % topics.ROTATION_SECONDS + 0.25)
            async with panel_lock:
                for key, (uid, topic, index) in list(topic_panels.items()):
                    index = (index + 1) % len(topics.TOPICS[topic][1])
                    text, markup = topics.topic_screen(topic, index=index)
                    try:
                        await app.bot.edit_message_text(
                            chat_id=key[0], message_id=key[1], text=text,
                            parse_mode="HTML", reply_markup=markup,
                        )
                        topic_panels[key] = (uid, topic, index)
                        pending_questions[uid] = (key, topics.starter(topic, index=index))
                    except BadRequest:
                        topic_panels.pop(key, None)
                    except Exception as error:
                        LOG.warning("Topic refresh failed (%s)", type(error).__name__)

    async def allowed(update):
        if not update.effective_message or not update.effective_user:
            return False
        if update.effective_chat.type != ChatType.PRIVATE:
            return False
        if settings.allowed_users and update.effective_user.id not in settings.allowed_users:
            await update.effective_message.reply_text("This bot is currently limited to approved learners.")
            return False
        reminders.touch(update.effective_user.id, update.effective_message.chat_id)
        return True

    async def command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if (update.effective_message and update.effective_user
                and update.effective_chat.type == ChatType.PRIVATE
                and update.effective_message.text.split()[0].split("@")[0].lower() == "/whoami"):
            await update.effective_message.reply_text(f"🪪 <b>Your Telegram ID</b>\n\n<code>{update.effective_user.id}</code>", parse_mode="HTML")
            return
        if not await allowed(update):
            return
        message = update.effective_message
        uid = update.effective_user.id
        name = message.text.split()[0].split("@")[0].lower()
        if name in ("/start", "/help", "/settings", "/topics", "/privacy", "/reset"):
            async with panel_lock:
                clear_topics(uid)
                pending_questions.pop(uid, None)
        voice, level = store.preferences(uid)
        if name == "/start":
            store.set_feedback_active(uid, False)
        if name in ("/start", "/help"):
            await message.reply_text(ui.HOME if name == "/start" else ui.HELP, parse_mode="HTML", reply_markup=ui.home_keyboard())
        elif name == "/privacy":
            await message.reply_text(ui.PRIVACY, parse_mode="HTML", reply_markup=ui.back_keyboard())
        elif name == "/topics":
            text, markup = ui.topics_screen()
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        elif name == "/settings":
            text, markup = ui.settings_screen(store, uid)
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        elif name == "/reminders":
            args = getattr(context, "args", [])
            note = ""
            try:
                if args in (["on"], ["off"]):
                    reminders.configure(uid, enabled=args[0] == "on")
                elif len(args) == 2 and args[0] == "time":
                    reminders.configure(uid, preferred_time=args[1])
                elif len(args) == 2 and args[0] == "timezone":
                    reminders.configure(uid, zone=args[1])
                elif args:
                    raise ValueError("Use /reminders, /reminders on, /reminders off, /reminders time 19:00, or /reminders timezone Europe/Kyiv.")
            except ValueError as error:
                note = escape(str(error)) + "\n\n"
            text, markup = reminder_screen(store.reminder_state(uid))
            await message.reply_text(note + text, parse_mode="HTML", reply_markup=markup)
        elif name == "/transcript":
            value = context.args[0].lower() if len(context.args) == 1 else ""
            if value not in ("on", "off"):
                text, markup = ui.settings_screen(store, uid)
                await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
                return
            store.set_show_transcript(uid, value == "on")
            text, markup = ui.settings_screen(store, uid)
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        elif name == "/reset":
            clear_topics(uid)
            pending_questions.pop(uid, None)
            store.reset(uid)
            await message.reply_text("🌱 <b>A fresh start</b>\n\nYour conversation and preferences are cleared. Send a message whenever you are ready.", parse_mode="HTML", reply_markup=ui.home_keyboard())
        elif name == "/voice":
            value = context.args[0].lower() if len(context.args) == 1 else ""
            if value not in ("on", "off"):
                text, markup = ui.settings_screen(store, uid)
                await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
                return
            store.set_preferences(uid, value == "on", level)
            text, markup = ui.settings_screen(store, uid)
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        elif name == "/level":
            value = context.args[0].upper() if len(context.args) == 1 else ""
            if value not in ("A1", "A2", "B1", "B2", "C1", "C2"):
                text, markup = ui.levels_screen(level)
                await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
                return
            store.set_preferences(uid, voice, value)
            text, markup = ui.settings_screen(store, uid)
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        elif name == "/feedback":
            await review(message, uid, context)
        elif name == "/chat":
            await leave_feedback(message, uid)

    async def review(message, uid, context, fresh=False):
        async with panel_lock:
            clear_topics(uid)
            pending_questions.pop(uid, None)
        session = store.feedback_session(uid)
        voice, level = store.preferences(uid)
        if session and not fresh:
            store.set_feedback_active(uid, True)
            reply = session["history"][-1]["content"] if session["history"] else session["review"]
            await deliver(message, reply, voice)
            return
        history = store.history(uid)
        if any(turn["role"] == "user" for turn in history):
            await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
            reply = await tutor.respond(history, level, feedback=True)
        else:
            reply = ui.FEEDBACK_INTRO
        # Only replace an existing lesson after its new review has succeeded.
        store.start_feedback(uid, history, reply)
        await deliver(message, reply, voice)

    async def coach(message, uid, context, text, track_practice=True):
        session = store.feedback_session(uid)
        if not session or not session["active"]:
            await message.reply_text(
                "This lesson is paused. Open Feedback mode to resume it.", reply_markup=ui.home_keyboard(),
            )
            return
        voice, level = store.preferences(uid)
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
        reply = await tutor.coach(session, text, level)
        store.append_feedback_turn(uid, text, reply)
        if track_practice and is_practice_reply(text):
            store.record_practice(uid)
        await deliver(message, reply, voice)

    async def leave_feedback(message, uid):
        store.set_feedback_active(uid, False)
        await message.reply_text(
            "💬 <b>Back to conversation</b>\n\nTalk about anything you like. "
            "Your feedback lesson is saved; open Feedback mode to resume it.",
            parse_mode="HTML", reply_markup=ui.home_keyboard(),
        )

    async def menu(update, context):
        action = update.callback_query.data.removeprefix("ui:")
        if action.startswith("reminder:"):
            if not await allowed(update):
                await update.callback_query.answer()
                return
            query = update.callback_query
            await query.answer()
            uid = update.effective_user.id
            if action == "reminder:practice":
                await review(query.message, uid, context)
                return
            if action == "reminder:preview":
                await query.edit_message_text(
                    "👀 <b>Reminder preview</b>\n\n" + reminder_message(store.reminder_state(uid), time.time()),
                    parse_mode="HTML", reply_markup=reminder_keyboard(),
                )
                return
            note = ""
            try:
                if action in ("reminder:on", "reminder:off"):
                    reminders.configure(uid, enabled=action == "reminder:on")
                elif action == "reminder:tomorrow":
                    if store.reminder_state(uid)["enabled"]:
                        reminders.snooze(uid)
                        note = "⏰ We’ll try tomorrow at your chosen time, within your daily and weekly limits.\n\n"
                    else:
                        note = "😴 Reminders are paused. Enable them to schedule another invitation.\n\n"
                elif action.startswith("reminder:time:"):
                    reminders.configure(uid, preferred_time=action.removeprefix("reminder:time:"))
                elif action.startswith("reminder:zone:"):
                    reminders.configure(uid, zone=action.removeprefix("reminder:zone:"))
            except ValueError as error:
                note = escape(str(error)) + "\n\n"
            text, markup = reminder_screen(store.reminder_state(uid))
            try:
                await query.edit_message_text(note + text, parse_mode="HTML", reply_markup=markup)
            except BadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
            return
        if action == "feedback" or action.startswith("feedback:"):
            if not await allowed(update):
                await update.callback_query.answer()
                return
            await update.callback_query.answer()
            uid = update.effective_user.id
            message = update.callback_query.message
            if action in ("feedback", "feedback:new"):
                await review(message, uid, context, fresh=action.endswith(":new"))
            elif action == "feedback:exit":
                await leave_feedback(message, uid)
            elif action in ("feedback:explain", "feedback:example", "feedback:practice"):
                await coach(message, uid, context, "[Lesson action: " + action.split(":")[1] + "]", track_practice=False)
            return
        async with panel_lock:
            await handle_menu(update, context)

    async def handle_menu(update, context):
        query = update.callback_query
        if not await allowed(update):
            await query.answer()
            return
        await query.answer()
        uid = update.effective_user.id
        key = (query.message.chat_id, query.message.message_id)
        previous_panel = topic_panels.pop(key, None)
        if pending_questions.get(uid, (None,))[0] == key:
            pending_questions.pop(uid, None)
        action = query.data.removeprefix("ui:")
        question_index = None
        if action.startswith("refresh:"):
            parts = action.split(":")
            if len(parts) != 3 or parts[1] not in topics.TOPICS or not parts[2].isdigit():
                return
            topic = parts[1]
            displayed_index = int(parts[2])
            if not 0 <= displayed_index < len(topics.TOPICS[topic][1]):
                return
            # Prefer current state if a delayed button belongs to an older screen.
            if previous_panel and previous_panel[1] == topic:
                displayed_index = previous_panel[2]
            question_index = (displayed_index + 1) % len(topics.TOPICS[topic][1])
            action = "topic:" + topic
        voice, level = store.preferences(uid)
        if action.startswith("voice:") and action[6:] in ("0", "1"):
            store.set_preferences(uid, action[6:] == "1", level)
            action = "settings"
        elif action.startswith("transcript:") and action[11:] in ("0", "1"):
            store.set_show_transcript(uid, action[11:] == "1")
            action = "settings"
        elif action.startswith("level:") and action[6:] in ("A1", "A2", "B1", "B2", "C1", "C2"):
            store.set_preferences(uid, voice, action[6:])
            action = "settings"
        if action == "settings":
            text, markup = ui.settings_screen(store, uid)
        elif action == "levels":
            text, markup = ui.levels_screen(level)
        elif action == "topics":
            text, markup = ui.topics_screen()
        elif action.startswith("topic:") and action[6:] in topics.TOPICS:
            store.set_feedback_active(uid, False)
            topic = action[6:]
            if question_index is None:
                # Support Refresh buttons on screens sent before this update too.
                question_index = ((previous_panel[2] + 1) % len(topics.TOPICS[topic][1])
                                  if previous_panel and previous_panel[1] == topic
                                  else topics.rotation_index(topic))
            clear_topics(uid)
            text, markup = topics.topic_screen(topic, index=question_index)
            topic_panels[key] = (uid, topic, question_index)
            pending_questions[uid] = (key, topics.starter(topic, index=question_index))
        elif action in ("home", "help", "privacy"):
            if action == "home":
                store.set_feedback_active(uid, False)
            text = {"home": ui.HOME, "help": ui.HELP, "privacy": ui.PRIVACY}[action]
            markup = ui.home_keyboard() if action == "home" else ui.back_keyboard()
        else:
            return
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except BadRequest as error:
            if "message is not modified" not in str(error).lower():
                raise

    async def deliver(message, reply, voice):
        await send_text(message, reply, feedback=True)
        if voice:
            await send_voice_reply(message, reply, tutor.speech)

    async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await allowed(update):
            return
        message = update.effective_message
        uid = update.effective_user.id
        # Freeze the displayed question as soon as a learner sends an answer.
        async with panel_lock:
            clear_topics(uid)
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
        if message.voice:
            # Leave room below both Telegram download and Gemini inline upload limits.
            if message.voice.duration > 180 or (message.voice.file_size or 0) > 10_000_000:
                await message.reply_text("Please send a voice message under 3 minutes and 10 MB.")
                return
            file = await message.voice.get_file()
            audio = await file.download_as_bytearray()
            if len(audio) > 10_000_000:
                await message.reply_text("That recording is too large. Please send a shorter one.")
                return
            text = await tutor.transcribe(bytes(audio))
            if not text:
                await message.reply_text("I couldn't hear any words. Please try another recording.")
                return
            if len(text) > 6000:
                await message.reply_text("Please send a shorter recording so we can practise one idea at a time.")
                return
            if store.show_transcript(uid):
                for start in range(0, len(text), 4000):
                    await message.reply_text("🎧 <b>I heard</b>\n\n" + escape(text[start:start + 4000]), parse_mode="HTML")
        else:
            text = (message.text or "").strip()
            if not text:
                return
            if len(text) > 6000:
                await message.reply_text("Please keep each message under 6,000 characters.")
                return
        voice, level = store.preferences(uid)
        session = store.feedback_session(uid)
        if session and session["active"]:
            await coach(message, uid, context, text)
            return
        if uid in pending_questions:
            _, question = pending_questions.pop(uid)
            store.append_prompt(uid, question)
        history = store.history(uid) + [{"role": "user", "content": text}]
        reply = await tutor.respond(history, level)
        await send_text(message, reply)
        store.append_turn(uid, text, reply)
        if voice:
            # The text has already been delivered and saved; speech is optional.
            await send_voice_reply(message, reply, tutor.speech)
        await reminders.maybe_nudge(context.bot, uid, text)

    async def on_error(update, context):
        # Avoid logging exception strings, which can contain tokens or message content.
        LOG.error("Request failed (%s)", type(context.error).__name__)
        if isinstance(context.error, QuotaExceeded):
            notice = ("Gemini's free usage limit has been reached. Please try again later; "
                      "the bot owner can check when the quota resets in Google AI Studio.")
        else:
            notice = ("I couldn't complete that request. Please try again shortly. "
                      "If it keeps happening, ask the bot owner to check Gemini API access and free-tier quota.")
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(notice)
            except Exception:
                LOG.error("Could not send error notice")

    async def startup(app):
        nonlocal refresh_task, reminder_task
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await app.bot.set_my_short_description("Your English space. Voice chats, curious questions, and helpful feedback.")
        await app.bot.set_my_description(
            "Practise English through real conversations. Send a voice note or a message, "
            "explore any topic, and get clear feedback when you want it. "
            "Choose your English level and turn spoken replies on in Settings."
        )
        await app.bot.set_my_commands([
            BotCommand("start", "Start practising English"),
            BotCommand("topics", "Find a conversation starter"),
            BotCommand("feedback", "Enter or resume feedback practice"),
            BotCommand("chat", "Leave feedback and return to conversation"),
            BotCommand("voice", "Turn spoken replies on or off"),
            BotCommand("settings", "View your settings"),
            BotCommand("reminders", "Choose quiet practice reminders"),
            BotCommand("transcript", "Show or hide I heard transcripts"),
            BotCommand("level", "Set your English level"),
            BotCommand("reset", "Delete saved conversation and settings"),
            BotCommand("whoami", "Show your Telegram user ID"),
            BotCommand("privacy", "Message and audio privacy"),
            BotCommand("help", "Show help"),
        ])
        refresh_task = asyncio.create_task(refresh_topics(app))
        reminder_task = asyncio.create_task(reminders.run(app.bot))

    async def shutdown(app):
        for task in (refresh_task, reminder_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await tutor.close()
        store.close()

    # Sequential processing preserves turn order and avoids SQLite/thread races.
    app = (Application.builder().token(settings.telegram_token)
           .concurrent_updates(False).post_init(startup).post_shutdown(shutdown).build())
    app.add_handler(CommandHandler(["start", "help", "whoami", "privacy", "reset", "voice", "settings", "transcript", "level", "feedback", "topics", "chat", "reminders"], command))
    app.add_handler(CallbackQueryHandler(menu, pattern=r"^ui:"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.VOICE | (filters.TEXT & ~filters.COMMAND)), chat))
    app.add_error_handler(on_error)
    return app


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = Settings.load()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    try:
        create_application(settings).run_polling(allowed_updates=["message", "callback_query"])
    except InvalidToken:
        raise SystemExit("Telegram rejected TELEGRAM_BOT_TOKEN. Update it using @BotFather.") from None

