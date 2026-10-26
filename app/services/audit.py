"""Audit log in SQLite. Everything is sanitised before it is written."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from app.database import Database, utc_now
from app.security.validators import safe_tool_label, sanitize_arguments


class AuditService:
    def __init__(self, db: Database):
        self.db = db

    def record(self, *, request_id: str, tool_name: Any, decision: str, execution_status: str,
               reason: str, arguments: Any = None, duration_ms: Optional[float] = None,
               actor: Optional[str] = None) -> str:
        event_id = uuid.uuid4().hex
        summary = json.dumps(sanitize_arguments(arguments if arguments is not None else {}))
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO audit_events (event_id, request_id, timestamp, tool_name, decision,"
                " execution_status, reason, arguments_summary, duration_ms, actor)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_id, str(request_id)[:64], utc_now(), safe_tool_label(tool_name),
                 str(decision), str(execution_status), str(reason)[:300], summary,
                 duration_ms, (str(actor)[:64] if actor else None)),
            )
        return event_id

    def list(self, decision: Optional[str] = None, tool_name: Optional[str] = None,
             limit: int = 50, offset: int = 0) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        sql, params = "SELECT * FROM audit_events WHERE 1=1", []
        if decision:
            sql += " AND decision = ?"
            params.append(decision)
        if tool_name:
            sql += " AND tool_name = ?"
            params.append(tool_name)
        sql += " ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self.db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["arguments_summary"] = json.loads(d["arguments_summary"])
            out.append(d)
        return out

    def metrics(self) -> dict:
        with self.db.connect() as c:
            r = c.execute(
                "SELECT"
                " COALESCE(SUM(decision IN ('ALLOWED','BLOCKED','PENDING_APPROVAL')),0) AS total,"
                " COALESCE(SUM(decision='ALLOWED'),0) AS allowed,"
                " COALESCE(SUM(decision='BLOCKED'),0) AS blocked,"
                " COALESCE(SUM(execution_status='FAILED'),0) AS failed,"
                " COALESCE(SUM(decision='APPROVED'),0) AS approved,"
                " COALESCE(SUM(decision='REJECTED'),0) AS rejected"
                " FROM audit_events").fetchone()
        return {"total_requests": r["total"], "allowed": r["allowed"], "blocked": r["blocked"],
                "failed_executions": r["failed"], "approvals_approved": r["approved"],
                "approvals_rejected": r["rejected"]}
