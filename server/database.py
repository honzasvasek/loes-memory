import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, type TEXT NOT NULL CHECK(type IN ('profile','episodic')),
                    text TEXT NOT NULL, embedding BLOB NOT NULL,
                    importance REAL NOT NULL, confidence REAL NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    last_used_at TEXT, use_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, query='', kind=None):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM memories WHERE instr(lower(text),lower(?)) > 0 '
                'AND (? IS NULL OR type=?) ORDER BY id DESC', (query, kind, kind))]

    def delete(self, memory_id):
        with self.connect() as db:
            return db.execute('DELETE FROM memories WHERE id=?', (memory_id,)).rowcount > 0

    def update_importance(self, memory_id, importance):
        with self.connect() as db:
            return db.execute('UPDATE memories SET importance=?, updated_at=? WHERE id=?',
                              (importance, now(), memory_id)).rowcount > 0


def public(row):
    return {key: value for key, value in row.items() if key != 'embedding'}
