import hashlib
import json
import math
from datetime import datetime, timezone
from threading import Lock
import numpy as np
from .database import now, public
from .embeddings import similarity


class MemoryService:
    def __init__(self, db, embeddings, llm, settings):
        self.db, self.embeddings, self.llm, self.settings = db, embeddings, llm, settings
        self.lock = Lock()
        with db.connect() as conn:
            model = conn.execute("SELECT value FROM metadata WHERE key='embedding_model'").fetchone()
            if model and model['value'] != settings.embedding_model:
                raise ValueError('Gebruik bij een ander embeddingmodel een nieuwe DATABASE_PATH')
            conn.execute("INSERT OR IGNORE INTO metadata VALUES ('embedding_model',?)", (settings.embedding_model,))

    def _insert(self, conn, item, vector):
        # Conservative deduplication: keep existing text; never silently overwrite a fact.
        for row in conn.execute('SELECT * FROM memories WHERE type=?', (item.type,)):
            if (row['text'].casefold() == item.text.casefold() or
                similarity(vector, np.frombuffer(row['embedding'], dtype=np.float32)) > self.settings.dedup_threshold):
                return public(dict(row)), False
        stamp = now()
        cursor = conn.execute('''INSERT INTO memories
            (type,text,embedding,importance,confidence,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)''', (item.type, item.text, vector.tobytes(), item.importance,
                                       item.confidence, stamp, stamp))
        return public(dict(conn.execute('SELECT * FROM memories WHERE id=?', (cursor.lastrowid,)).fetchone())), True

    def add(self, item):
        vector = self.embeddings.encode(item.text)
        with self.lock, self.db.connect() as conn:
            return self._insert(conn, item, vector)

    def import_memories(self, items):
        # Embed before writing; one transaction makes failed imports all-or-nothing.
        vectors = [self.embeddings.encode(item.text) for item in items]
        with self.lock, self.db.connect() as conn:
            # Also serialize against a running daemon / other import processes.
            conn.execute('BEGIN IMMEDIATE')
            added = sum(self._insert(conn, item, vector)[1]
                        for item, vector in zip(items, vectors))
        return {'added': added, 'duplicates': len(items) - added}

    def recall(self, message):
        rows = self.db.rows()
        if not rows:
            return []
        vector = self.embeddings.encode(message)
        ranked = []
        current = datetime.now(timezone.utc)
        for row in rows:
            semantic = similarity(vector, np.frombuffer(row['embedding'], dtype=np.float32))
            if semantic < self.settings.recall_min_similarity:
                continue
            days = max(0, (current - datetime.fromisoformat(row['updated_at'])).total_seconds() / 86400)
            recency = math.exp(-days / 90)
            frequency = min(math.log1p(row['use_count']) / math.log(21), 1)
            score = .65 * semantic + .20 * row['importance'] + .10 * recency + .05 * frequency
            ranked.append((score, row))
        chosen, size = [], 0
        for _, row in sorted(ranked, key=lambda pair: pair[0], reverse=True):
            if size + len(row['text']) > self.settings.recall_max_chars:
                continue
            # Do not spend the context budget on paraphrases, even across types.
            candidate = np.frombuffer(row['embedding'], dtype=np.float32)
            if any(similarity(candidate, np.frombuffer(other['embedding'], dtype=np.float32))
                   > self.settings.dedup_threshold for other in chosen):
                continue
            chosen.append(row)
            size += len(row['text'])
            if len(chosen) >= self.settings.recall_limit:
                break
        with self.db.connect() as conn:
            conn.executemany('UPDATE memories SET last_used_at=?, use_count=use_count+1 WHERE id=?',
                             [(now(), row['id']) for row in chosen])
        return [row['text'] for row in chosen]

    def observe(self, observation):
        # Persist only a digest, never the raw conversation. Retry-safe across restarts.
        identity = json.dumps([observation.observation_id, observation.user, observation.assistant])
        digest = hashlib.sha256(identity.encode()).hexdigest()
        with self.lock:
            with self.db.connect() as conn:
                if conn.execute('SELECT 1 FROM observations WHERE id=?', (digest,)).fetchone():
                    return {'status': 'duplicate', 'added': 0}
            extracted = self.llm.extract(observation.user, observation.assistant)
            items = [m for m in extracted.memories if m.confidence >= self.settings.extraction_min_confidence
                     and m.importance >= self.settings.extraction_min_importance]
            vectors = [self.embeddings.encode(m.text) for m in items]
            with self.db.connect() as conn:
                added = sum(self._insert(conn, item, vector)[1] for item, vector in zip(items, vectors))
                conn.execute('INSERT INTO observations VALUES (?,?)', (digest, now()))
            return {'status': 'ok', 'added': added}
