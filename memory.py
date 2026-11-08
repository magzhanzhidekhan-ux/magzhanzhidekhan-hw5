import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def storage_dir(path=None) -> Path:
    p = Path(path or os.getenv("HELPDESK_STORAGE_DIR", "local-storage"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def reset_storage(path=None):
    """Delete checkpoints, user memory and ticket drafts."""
    p = Path(path or os.getenv("HELPDESK_STORAGE_DIR", "local-storage"))
    shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True, exist_ok=True)


class UserMemory:
    """Persistent per-user preferences (separate from conversation checkpoints)."""

    def __init__(self, path=None):
        self.db = storage_dir(path) / "user_memory.sqlite"
        self._run("CREATE TABLE IF NOT EXISTS user_prefs ("
                  "user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
                  "PRIMARY KEY (user_id, key))")

    def _run(self, sql, params=()):
        with closing(sqlite3.connect(self.db)) as conn:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows

    def get_all(self, user_id: str) -> dict:
        rows = self._run("SELECT key, value FROM user_prefs WHERE user_id = ?", (user_id,))
        return dict(rows)

    def set(self, user_id: str, key: str, value: str):
        self._run("INSERT INTO user_prefs (user_id, key, value) VALUES (?, ?, ?) "
                  "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                  (user_id, key, value))