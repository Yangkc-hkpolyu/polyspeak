import json
from pathlib import Path
import sqlite3


class ConflictError(RuntimeError):
    pass


class InterviewStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, session: dict):
        session["version"] = 0
        with self.connect() as db:
            db.execute("INSERT INTO interviews VALUES (?, ?, ?)", (session["id"], 0, json.dumps(session, ensure_ascii=False)))

    def get(self, session_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM interviews WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        return json.loads(row[0])

    def save(self, session: dict):
        version = session["version"]
        updated = {**session, "version": version + 1}
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE interviews SET version = ?, data = ? WHERE id = ? AND version = ?",
                (version + 1, json.dumps(updated, ensure_ascii=False), session["id"], version),
            )
            if cursor.rowcount != 1:
                raise ConflictError("这轮回答已经处理，请刷新面试状态后继续。")
        session["version"] = version + 1

