"""Opt-in, quiet practice invitations with durable limits and real activity times."""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram.error import Forbidden

LOG = logging.getLogger(__name__)
DAY = 86400
WEEK = 7 * DAY


def local_time(now, zone):
    return datetime.fromtimestamp(now, timezone.utc).astimezone(ZoneInfo(zone))


def validate_time(value):
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("Use a time like 19:00.")
    hour, minute = map(int, value.split(":"))
    if not 9 <= hour < 21 or not 0 <= minute < 60:
        raise ValueError("Choose a time between 09:00 and 20:59 to keep nights quiet.")


def validate_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use a timezone such as Europe/Kyiv, Europe/London, or America/New_York.") from None


def next_regular(now, zone, preferred_time):
    current = local_time(now, zone)
    hour, minute = map(int, preferred_time.split(":"))
    for offset in range(8):
        candidate = (current + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.weekday() in (1, 4) and candidate.timestamp() > now:
            return candidate.timestamp()
    raise ValueError("Could not schedule practice reminder")


def tomorrow(now, zone, preferred_time):
    hour, minute = map(int, preferred_time.split(":"))
    return (local_time(now, zone) + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def elapsed_label(last_practiced, now=None):
    if last_practiced is None:
        return "No practice recorded yet"
    seconds = max(0, int((time.time() if now is None else now) - last_practiced))
    days, remainder = divmod(seconds, DAY)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} day{'s' if days != 1 else ''}" + (f", {hours} hour{'s' if hours != 1 else ''}" if hours else "") + " ago"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if minutes:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    return "Just now"


def is_practice_reply(text):
    normal = " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())
    return bool(normal) and normal not in {"ok", "okay", "thanks", "thank you", "thanks so much", "thank you very much", "got it", "understood"}


def reminder_keyboard():
    from .ui import keyboard
    return keyboard([
        [("🌟 Practise now", "reminder:practice")],
        [("⏰ Tomorrow", "reminder:tomorrow"), ("😴 Pause reminders", "reminder:off")],
        [("⚙️ Reminder settings", "reminder:menu")],
    ])


def reminder_message(state, now):
    last = state["last_practiced"]
    gap = now - last if last is not None else None
    if gap is None:
        title = "🦉 Ready for a tiny English workout?"
        body = "One sentence. One useful pattern. A little more confidence. 🌱"
    elif gap >= WEEK:
        title = "🌱 A fresh start is always welcome"
        body = "Your English space is right here. One small practice round is a lovely way back. 💬"
    else:
        choices = (
            ("🦉 Your next English adventure?", "A quick sentence challenge is a small step with a useful payoff. ✨"),
            ("🧩 Fancy a tiny sentence puzzle?", "Let's turn one tricky pattern into something that feels natural. 💡"),
            ("🌟 A little practice, a little progress", "Your saved lesson is ready for another small step. 🐾"),
            ("📚 One sentence closer to confidence", "A familiar pattern, a fresh example, and a chance to make it yours. ✨"),
            ("🌿 Time for a small English stretch?", "One useful idea from your lesson can become easier with a little practice. 💬"),
        )
        title, body = choices[int(now // DAY) % len(choices)]
    age = "" if last is None else "\n\n⏳ <b>Last practice:</b> " + elapsed_label(last, now)
    return f"<b>{title}</b>\n\n{body}{age}\n\n<i>One small round? You can snooze or pause anytime.</i>"


def reminder_screen(state, now=None):
    from .ui import keyboard
    now = time.time() if now is None else now
    status = "On · twice a week" if state["enabled"] else ("Paused after two unanswered reminders" if state["auto_paused"] else "Off")
    text = (
        "🦉 <b>A little practice goes a long way</b>\n\n"
        f"<b>Reminders</b>  {status}\n"
        f"<b>Schedule</b>  Tuesday &amp; Friday · {state['preferred_time']}\n"
        f"<b>Timezone</b>  {escape(state['timezone'])}\n\n"
        f"⏳ <b>Last feedback practice</b>\n{elapsed_label(state['last_practiced'], now)}\n\n"
        "A text or voice answer/question in feedback mode updates this clock. "
        "Opening a lesson or tapping an example button does not.\n\n"
        "Invitations appear only when a saved lesson or new conversation is ready to revisit.\n\n"
        "🔕 Silent invitations, never overnight. At most one a day and two in seven days, "
        "including chat invitations. We skip days you've practised, and pause after two "
        "unanswered reminders until you return.\n\n"
        "<i>Choose a time below. For another time or timezone, send:</i>\n"
        "<code>/reminders time 18:30</code>\n<code>/reminders timezone Europe/Kyiv</code>"
    )
    return text, keyboard([
        [("😴 Turn reminders off" if state["enabled"] else "🌟 Enable reminders", "reminder:off" if state["enabled"] else "reminder:on")],
        [(label, "reminder:time:" + label) for label in ("18:00", "19:00", "20:00")],
        [("🇺🇦 Kyiv", "reminder:zone:Europe/Kyiv"), ("🇬🇧 London", "reminder:zone:Europe/London")],
        [("🇺🇸 New York", "reminder:zone:America/New_York"), ("🌐 UTC", "reminder:zone:UTC")],
        [("👀 Preview reminder", "reminder:preview")],
        [("📝 Feedback mode", "feedback"), ("‹ Settings", "settings")],
    ])


class ReminderService:
    def __init__(self, store, allowed_users=frozenset(), clock=time.time):
        self.store = store
        self.allowed_users = allowed_users
        self.clock = clock

    def touch(self, uid, chat_id):
        now = self.clock()
        state = self.store.reminder_state(uid)
        values = {"chat_id": chat_id, "last_seen": now, "unanswered": 0}
        if state["auto_paused"]:
            values.update(enabled=1, auto_paused=0, next_due=next_regular(now, state["timezone"], state["preferred_time"]))
        self.store.update_reminders(uid, **values)

    def configure(self, uid, *, enabled=None, preferred_time=None, zone=None):
        state = self.store.reminder_state(uid)
        if preferred_time is not None:
            validate_time(preferred_time)
            state["preferred_time"] = preferred_time
        if zone is not None:
            validate_zone(zone)
            state["timezone"] = zone
        if enabled is not None:
            state["enabled"] = int(enabled)
        self.store.update_reminders(
            uid, enabled=state["enabled"], auto_paused=0, unanswered=0,
            preferred_time=state["preferred_time"], timezone=state["timezone"],
            next_due=next_regular(self.clock(), state["timezone"], state["preferred_time"]) if state["enabled"] else None,
        )

    def snooze(self, uid):
        state = self.store.reminder_state(uid)
        if state["enabled"]:
            self.store.update_reminders(uid, next_due=tomorrow(self.clock(), state["timezone"], state["preferred_time"]))

    def has_material(self, state):
        if state["new_messages"] >= 10:
            return True
        session = self.store.feedback_session(state["user_id"])
        return bool(session and (
            any(turn["role"] == "user" for turn in session["source"])
            or any(turn["role"] == "user" and not turn["content"].startswith("[Lesson action:") for turn in session["history"])
        ))

    def eligible(self, state, now, *, contextual=False):
        if not state["enabled"] or state["chat_id"] is None:
            return False
        if self.allowed_users and state["user_id"] not in self.allowed_users:
            return False
        current = local_time(now, state["timezone"])
        if not 9 <= current.hour < 21 or not self.has_material(state):
            return False
        if not contextual and now - state["last_seen"] < 1800:
            return False
        last = state["last_practiced"]
        if last is not None and local_time(last, state["timezone"]).date() == current.date():
            return False
        deliveries = self.store.recent_reminders(state["user_id"], now - WEEK)
        if len(deliveries) >= 2 or any(local_time(row[0], state["timezone"]).date() == current.date() for row in deliveries):
            return False
        return True

    async def send(self, bot, state, now, *, contextual=False):
        uid = state["user_id"]
        state = self.store.reminder_state(uid)
        if not self.eligible(state, now, contextual=contextual):
            return False
        # Advance even a future slot used by a contextual nudge, so claims differ.
        next_due = next_regular(max(now, state["next_due"] or now), state["timezone"], state["preferred_time"])
        claim = self.store.claim_reminder(uid, now, next_due, expected_due=state["next_due"])
        if claim is None:
            return False
        try:
            await bot.send_message(
                chat_id=state["chat_id"], text=reminder_message(state, now),
                parse_mode="HTML", reply_markup=reminder_keyboard(), disable_notification=True,
            )
        except Forbidden:
            self.store.finish_reminder(uid, claim, False, state["last_seen"])
            self.configure(uid, enabled=False)
            return False
        except Exception as error:
            self.store.finish_reminder(uid, claim, False, state["last_seen"])
            LOG.warning("Practice reminder failed (%s)", type(error).__name__)
            return False
        self.store.finish_reminder(uid, claim, True, state["last_seen"])
        return True

    async def tick(self, bot):
        now = self.clock()
        for state in self.store.reminder_candidates(now):
            state = self.store.reminder_state(state["user_id"])
            if not state["enabled"] or state["next_due"] is None or state["next_due"] > now:
                continue
            if now - state["next_due"] > 3600 or not self.eligible(state, now):
                self.store.update_reminders(state["user_id"], next_due=next_regular(now, state["timezone"], state["preferred_time"]))
                continue
            await self.send(bot, state, now)

    async def maybe_nudge(self, bot, uid, text):
        # Only a short, natural closing after enough new conversation.
        if not re.fullmatch(
            r"\s*(?:(?:thanks|thank you)(?: so much| very much| for (?:your help|the help|today|the chat|this|that))?"
            r"|that(?:'s| is) all(?: for today)?|bye|goodbye|talk later|see you(?: later)?)[.! ,\s]*",
            text, re.IGNORECASE,
        ):
            return
        state = self.store.reminder_state(uid)
        now = self.clock()
        if state["new_messages"] >= 10 and self.eligible(state, now, contextual=True):
            await self.send(bot, state, now, contextual=True)

    async def run(self, bot, sleep=asyncio.sleep):
        while True:
            await sleep(60)
            try:
                await self.tick(bot)
            except Exception as error:
                LOG.warning("Reminder scheduler failed (%s)", type(error).__name__)
