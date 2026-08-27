import base64
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Spool:
    def __init__(self, path, max_items=10000):
        self.path = Path(path)
        self.max_items = max_items
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def push(self, payload):
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO queue(payload) VALUES (?)",
                (self._encode(payload),),
            )
            overflow = connection.execute(
                "SELECT MAX(COUNT(*) - ?, 0) FROM queue", (self.max_items,)
            ).fetchone()[0]
            if overflow:
                connection.execute(
                    "DELETE FROM queue WHERE id IN (SELECT id FROM queue ORDER BY id LIMIT ?)",
                    (overflow,),
                )

    def peek(self, limit=25):
        with self._connection() as connection:
            return [
                (row[0], self._decode(row[1]))
                for row in connection.execute(
                    "SELECT id, payload FROM queue ORDER BY id LIMIT ?", (limit,)
                )
            ]

    def delete(self, row_id):
        with self._connection() as connection:
            connection.execute("DELETE FROM queue WHERE id=?", (row_id,))

    def count(self):
        with self._connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0]

    @staticmethod
    def _encode(payload):
        serialized = json.dumps(payload, separators=(",", ":")).encode()
        if os.name != "nt":
            return serialized.decode()
        import win32crypt

        protected = win32crypt.CryptProtectData(
            serialized, "InfraSentinel metric spool", None, None, None, 0
        )
        return "dpapi:" + base64.b64encode(protected).decode()

    @staticmethod
    def _decode(payload):
        if not payload.startswith("dpapi:"):
            return json.loads(payload)
        if os.name != "nt":
            raise RuntimeError("Le spool DPAPI ne peut être lu que sous Windows.")
        import win32crypt

        protected = base64.b64decode(payload[6:])
        serialized = win32crypt.CryptUnprotectData(
            protected, None, None, None, 0
        )[1]
        return json.loads(serialized)
