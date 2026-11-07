import sqlite3
import json
import time
from pathlib import Path


class Store:
    """Bounded local history; each private conversation belongs to one user."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_user ON messages(user_id, id);
            CREATE TABLE IF NOT EXISTS preferences (
                user_id INTEGER PRIMARY KEY, voice INTEGER NOT NULL DEFAULT 0,
                level TEXT NOT NULL DEFAULT 'B1');
            CREATE TABLE IF NOT EXISTS feedback_sessions (
                user_id INTEGER PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL, review TEXT NOT NULL,
                history TEXT NOT NULL DEFAULT '[]');
            CREATE TABLE IF NOT EXISTS reminder_state (
                user_id INTEGER PRIMARY KEY, chat_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 0, auto_paused INTEGER NOT NULL DEFAULT 0,
                timezone TEXT NOT NULL DEFAULT 'Europe/Kyiv', preferred_time TEXT NOT NULL DEFAULT '19:00',
                last_seen REAL NOT NULL DEFAULT 0, last_practiced REAL,
                new_messages INTEGER NOT NULL DEFAULT 0, next_due REAL,
                unanswered INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS reminder_deliveries (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                attempted_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'attempted');
            CREATE INDEX IF NOT EXISTS reminder_delivery_user ON reminder_deliveries(user_id, attempted_at);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(preferences)")}
        if "show_transcript" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE preferences ADD COLUMN show_transcript INTEGER NOT NULL DEFAULT 0")

    def history(self, user_id: int):
        rows = self.db.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (user_id,),
        ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def append_turn(self, user_id: int, text: str, reply: str):
        with self.db:
            self.db.executemany(
                "INSERT INTO messages(user_id, role, content) VALUES (?, ?, ?)",
                [(user_id, "user", text), (user_id, "assistant", reply)],
            )
            self.db.execute(
                "DELETE FROM messages WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20)",
                (user_id, user_id),
            )
            self.db.execute("INSERT OR IGNORE INTO reminder_state(user_id) VALUES (?)", (user_id,))
            self.db.execute("UPDATE reminder_state SET new_messages=new_messages+1 WHERE user_id=?", (user_id,))

    def preferences(self, user_id: int):
        row = self.db.execute("SELECT voice, level FROM preferences WHERE user_id=?", (user_id,)).fetchone()
        return (bool(row[0]), row[1]) if row else (False, "B1")

    def append_prompt(self, user_id: int, text: str):
        """Save the starter actually answered, rather than every menu refresh."""
        with self.db:
            self.db.execute("INSERT INTO messages(user_id, role, content) VALUES (?, 'assistant', ?)", (user_id, text))
            self.db.execute(
                "DELETE FROM messages WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20)",
                (user_id, user_id),
            )

    def set_preferences(self, user_id: int, voice: bool, level: str):
        with self.db:
            self.db.execute(
                "INSERT INTO preferences(user_id, voice, level) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET voice=excluded.voice, level=excluded.level",
                (user_id, int(voice), level),
            )

    def show_transcript(self, user_id: int):
        row = self.db.execute("SELECT show_transcript FROM preferences WHERE user_id=?", (user_id,)).fetchone()
        return bool(row[0]) if row else False

    def set_show_transcript(self, user_id: int, enabled: bool):
        with self.db:
            self.db.execute(
                "INSERT INTO preferences(user_id, show_transcript) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET show_transcript=excluded.show_transcript",
                (user_id, int(enabled)),
            )

    def feedback_session(self, user_id: int):
        row = self.db.execute(
            "SELECT active, source, review, history FROM feedback_sessions WHERE user_id=?", (user_id,),
        ).fetchone()
        if not row:
            return None
        return {"active": bool(row[0]), "source": json.loads(row[1]), "review": row[2], "history": json.loads(row[3])}

    def start_feedback(self, user_id: int, source: list, review: str):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO feedback_sessions(user_id, active, source, review, history) "
                "VALUES (?, 1, ?, ?, '[]')",
                (user_id, json.dumps(source, ensure_ascii=False), review),
            )
            self.db.execute("UPDATE reminder_state SET new_messages=0 WHERE user_id=?", (user_id,))

    def set_feedback_active(self, user_id: int, active: bool):
        with self.db:
            self.db.execute("UPDATE feedback_sessions SET active=? WHERE user_id=?", (int(active), user_id))

    def append_feedback_turn(self, user_id: int, text: str, reply: str):
        session = self.feedback_session(user_id)
        if not session:
            raise ValueError("No feedback session")
        history = (session["history"] + [
            {"role": "user", "content": text}, {"role": "assistant", "content": reply},
        ])[-24:]
        with self.db:
            self.db.execute(
                "UPDATE feedback_sessions SET history=? WHERE user_id=?",
                (json.dumps(history, ensure_ascii=False), user_id),
            )

    def reminder_state(self, user_id: int):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO reminder_state(user_id) VALUES (?)", (user_id,))
        cursor = self.db.execute("SELECT * FROM reminder_state WHERE user_id=?", (user_id,))
        return dict(zip([field[0] for field in cursor.description], cursor.fetchone()))

    def update_reminders(self, user_id: int, **values):
        allowed = {"enabled", "auto_paused", "timezone", "preferred_time", "last_seen", "last_practiced", "new_messages", "next_due", "unanswered", "chat_id"}
        if not values or not set(values).issubset(allowed):
            raise ValueError("Invalid reminder fields")
        self.reminder_state(user_id)
        with self.db:
            self.db.execute(
                "UPDATE reminder_state SET " + ", ".join(field + "=?" for field in values) + " WHERE user_id=?",
                (*values.values(), user_id),
            )

    def record_practice(self, user_id: int, now=None):
        self.update_reminders(user_id, last_practiced=time.time() if now is None else now, unanswered=0)

    def reminder_candidates(self, now):
        rows = self.db.execute("SELECT user_id FROM reminder_state WHERE enabled=1 AND next_due<=? AND chat_id IS NOT NULL", (now,)).fetchall()
        return [self.reminder_state(row[0]) for row in rows]

    def recent_reminders(self, user_id: int, since):
        return self.db.execute(
            "SELECT attempted_at FROM reminder_deliveries WHERE user_id=? AND attempted_at>? ORDER BY attempted_at DESC",
            (user_id, since),
        ).fetchall()

    def claim_reminder(self, user_id: int, now, next_due, expected_due=None):
        """Reserve before network I/O: a restart cannot replay an uncertain send."""
        with self.db:
            cursor = self.db.execute(
                "UPDATE reminder_state SET next_due=? WHERE user_id=? AND enabled=1 AND chat_id IS NOT NULL "
                "AND next_due IS ?",
                (next_due, user_id, expected_due),
            )
            if not cursor.rowcount:
                return None
            cursor = self.db.execute(
                "INSERT INTO reminder_deliveries(user_id, attempted_at) VALUES (?, ?)", (user_id, now),
            )
            self.db.execute("DELETE FROM reminder_deliveries WHERE attempted_at<?", (now - 35 * 86400,))
            return cursor.lastrowid

    def finish_reminder(self, user_id: int, delivery_id: int, success: bool, seen_at_send: float):
        with self.db:
            self.db.execute("UPDATE reminder_deliveries SET status=? WHERE id=?", ("sent" if success else "failed", delivery_id))
            if success:
                # An interaction during a send acknowledges it; manual pauses stay paused.
                self.db.execute(
                    "UPDATE reminder_state SET unanswered=unanswered+1, "
                    "auto_paused=CASE WHEN unanswered+1>=2 AND enabled=1 THEN 1 ELSE auto_paused END, "
                    "enabled=CASE WHEN unanswered+1>=2 THEN 0 ELSE enabled END "
                    "WHERE user_id=? AND last_seen<=?",
                    (user_id, seen_at_send),
                )

    def reset(self, user_id: int):
        with self.db:
            self.db.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM feedback_sessions WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM reminder_state WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM reminder_deliveries WHERE user_id=?", (user_id,))

    def close(self):
        self.db.close()
