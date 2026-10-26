"""SQLite helper. A fresh connection per operation keeps it thread-safe and simple."""
from __future__ import annotations

import contextlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    tool_name TEXT,
    decision TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    arguments_summary TEXT NOT NULL,
    duration_ms REAL,
    actor TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_events(decision);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_events(tool_name);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""

_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(_FMT)


def utc_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(_FMT)


class Database:
    def __init__(self, path: str):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)

    @contextlib.contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def healthy(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False
