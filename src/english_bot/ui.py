"""Small, native Telegram screens and inline navigation."""

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup


def keyboard(rows):
    return InlineKeyboardMarkup([
        [Button(label, callback_data="ui:" + action) for label, action in row]
        for row in rows
    ])


HOME = (
    "💬 <b>Your English space</b>\n\n"
    "Send a voice note or type a message. Talk about your day, explore an idea, "
    "or ask me to explain something. You choose the topic.\n\n"
    "<b>Keep it natural</b>\n"
    "Short chats get short replies. Bigger questions get fuller explanations.\n\n"
    "<i>What would you like to talk about?</i>"
)

HELP = (
    "✨ <b>A little guide</b>\n\n"
    "<b>Talk your way</b>\nSend text or a voice note, up to 3 minutes / 10 MB. "
    "Ask for a shorter answer, more detail, or a different topic anytime.\n\n"
    "<b>Make it yours</b>\n/settings — voice replies, transcripts, and English level\n\n"
    "<b>Learn from your chats</b>\n/feedback — enter or resume guided feedback practice\n"
    "/chat — return to ordinary conversation\n\n"
    "<b>A gentle practice nudge</b>\n/reminders — optional, quiet practice reminders\n\n"
    "<b>Useful shortcuts</b>\n/start — home\n/whoami — your Telegram ID\n"
    "/reset — clear your conversation and preferences\n/privacy — how data is handled"
)

PRIVACY = (
    "🔒 <b>Your conversations &amp; privacy</b>\n\n"
    "<b>Processing</b>\nMessages and voice recordings go to Google Gemini. "
    "Google may use free-tier content to improve its products.\n\n"
    "<b>Spoken replies</b>\nGenerated locally on this server using Piper. "
    "Reply text is not sent to an external speech service.\n\n"
    "<b>Saved by this bot</b>\nYour last ten exchanges and preferences are stored "
    "locally. Feedback lessons also save their source examples, initial review, "
    "and latest twelve practice exchanges. Voice recordings stay in memory during processing.\n\n"
    "<b>Practice reminders</b>\nThe bot records your latest practice/interaction times "
    "and reminder choices to show your practice gap and avoid repeated invitations. "
    "Reminders are off until you enable them.\n\n"
    "<b>A fresh start</b>\n/reset clears your local conversation and preferences. "
    "It does not remove provider records or backups.\n\n"
    "<i>Spoken replies use an AI-generated voice.</i>"
)

def home_keyboard():
    return keyboard([
        [("🧭 Explore topics", "topics"), ("📝 Feedback mode", "feedback")],
        [("⚙️ Settings", "settings"), ("❔ How it works", "help")],
    ])


def back_keyboard():
    return keyboard([[("‹ Home", "home"), ("⚙️ Settings", "settings")]])


def feedback_keyboard():
    return keyboard([
        [("📖 Explain further", "feedback:explain"), ("💡 Another example", "feedback:example")],
        [("✍️ Next exercise", "feedback:practice")],
        [("🔄 Review latest chat", "feedback:new"), ("💬 Back to chat", "feedback:exit")],
        [("🦉 Practice reminders", "reminder:menu")],
    ])


FEEDBACK_INTRO = (
    "Your feedback starts here\n\n"
    "Feedback mode is on. Send an English sentence or a short paragraph, by text "
    "or voice. We will work on how you build sentences, express ideas, and connect "
    "them naturally, as well as grammar and vocabulary.\n\n"
    "I will explain the patterns and guide you through one exercise at a time. "
    "Ask questions whenever you need more detail. Use Back to chat or /chat to leave."
)


def settings_screen(store, uid):
    from .reminders import elapsed_label
    voice, level = store.preferences(uid)
    transcript = store.show_transcript(uid)
    session = store.feedback_session(uid)
    feedback_active = bool(session and session["active"])
    reminder = store.reminder_state(uid)
    text = (
        "⚙️ <b>Make it yours</b>\n\n"
        f"<b>Current mode</b>  {'Feedback practice' if feedback_active else 'Conversation'}\n\n"
        f"<b>Voice replies</b>  {'On' if voice else 'Off'}\n"
        "Listen to replies alongside the text.\n\n"
        f"<b>‘I heard’ transcript</b>  {'On' if transcript else 'Off'}\n"
        "Show what I understood from your voice note.\n\n"
        f"<b>English level</b>  {level}\n"
        "Choose the vocabulary and sentence difficulty.\n\n"
        f"🦉 <b>Practice reminders</b>  {'On' if reminder['enabled'] else 'Off'}\n"
        f"<b>Last feedback practice</b>  {elapsed_label(reminder['last_practiced'])}\n\n"
        "<i>Tap an option below. Your choices are saved just for you.</i>"
    )
    return text, keyboard([
        [(f"{'🔊' if voice else '🔇'} Voice: {'On' if voice else 'Off'}", f"voice:{int(not voice)}")],
        [(f"{'✓' if transcript else '○'} Transcript: {'On' if transcript else 'Off'}", f"transcript:{int(not transcript)}")],
        [(f"📚 Level: {level}", "levels")],
        [("🦉 Practice reminders", "reminder:menu")],
        [("💬 Back to chat" if feedback_active else "📝 Feedback mode", "feedback:exit" if feedback_active else "feedback")],
        [("‹ Home", "home"), ("🔒 Privacy", "privacy")],
    ])


def levels_screen(current):
    descriptions = (
        "A1 · First steps\nA2 · Everyday basics\nB1 · Comfortable conversations\n"
        "B2 · Express ideas in detail\nC1 · Nuanced discussions\nC2 · Fluent exploration"
    )
    rows = []
    for levels in [("A1", "A2", "B1"), ("B2", "C1", "C2")]:
        rows.append([(f"{'✓ ' if level == current else ''}{level}", "level:" + level) for level in levels])
    rows.append([("‹ Settings", "settings")])
    return "📚 <b>Your English level</b>\n\n" + descriptions + "\n\n<i>Choose a comfortable starting point.</i>", keyboard(rows)


def topics_screen():
    return (
        "🧭 <b>Follow your curiosity</b>\n\n"
        "Pick a starting point below, or simply send your own question.\n\n"
        "<i>Starter questions change every 30 minutes, or immediately when you tap Refresh. "
        "You can always choose a different subject.</i>",
        keyboard([
            [("☕ Everyday life", "topic:daily"), ("🏛 History", "topic:history")],
            [("💡 Science & ideas", "topic:science"), ("🌍 Culture & travel", "topic:culture")],
            [("📚 Work & learning", "topic:learning"), ("🌿 Nature", "topic:nature")],
            [("‹ Home", "home")],
        ]),
    )
