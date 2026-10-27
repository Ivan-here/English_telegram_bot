import sqlite3
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
        """)

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

    def preferences(self, user_id: int):
        row = self.db.execute("SELECT voice, level FROM preferences WHERE user_id=?", (user_id,)).fetchone()
        return (bool(row[0]), row[1]) if row else (False, "B1")

    def set_preferences(self, user_id: int, voice: bool, level: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?, ?)", (user_id, int(voice), level))

    def reset(self, user_id: int):
        with self.db:
            self.db.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))

    def close(self):
        self.db.close()
