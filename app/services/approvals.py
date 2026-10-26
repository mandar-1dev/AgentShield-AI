"""Human-approval store with atomic, single-use state transitions."""
from __future__ import annotations

import json
import uuid
from typing import Optional

from app.database import Database, utc_in, utc_now
from app.security.validators import sanitize_arguments

# PENDING -> APPROVED -> EXECUTED | FAILED ;  PENDING -> REJECTED | EXPIRED


class ApprovalError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ApprovalService:
    def __init__(self, db: Database, ttl_seconds: int):
        self.db = db
        self.ttl = ttl_seconds

    def create(self, request_id: str, tool_name: str, arguments: dict) -> str:
        approval_id = uuid.uuid4().hex
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO approvals (id, request_id, tool_name, arguments_json, status,"
                " created_at, expires_at) VALUES (?,?,?,?, 'PENDING', ?, ?)",
                (approval_id, request_id, tool_name, json.dumps(arguments), utc_now(),
                 utc_in(self.ttl)))
        return approval_id

    @staticmethod
    def _public(row) -> dict:
        d = dict(row)
        d["arguments"] = sanitize_arguments(json.loads(d.pop("arguments_json")))
        return d

    def get(self, approval_id: str) -> Optional[dict]:
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return self._public(row) if row else None

    def get_raw_arguments(self, approval_id: str) -> dict:
        with self.db.connect() as c:
            row = c.execute("SELECT arguments_json FROM approvals WHERE id = ?",
                            (approval_id,)).fetchone()
        return json.loads(row["arguments_json"])

    def list(self, status: Optional[str] = None, limit: int = 100) -> list[dict]:
        sql, params = "SELECT * FROM approvals", []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [self._public(r) for r in rows]

    def pending_count(self) -> int:
        with self.db.connect() as c:
            return c.execute("SELECT COUNT(*) FROM approvals WHERE status='PENDING' AND expires_at > ?",
                             (utc_now(),)).fetchone()[0]

    def claim(self, approval_id: str, new_status: str, decided_by: str) -> dict:
        """Atomically move PENDING -> APPROVED/REJECTED. Succeeds at most once."""
        error: Optional[ApprovalError] = None
        row = None
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                error = ApprovalError(404, "Unknown approval request")
            elif row["status"] == "PENDING" and row["expires_at"] <= utc_now():
                c.execute("UPDATE approvals SET status='EXPIRED' WHERE id=? AND status='PENDING'",
                          (approval_id,))
                error = ApprovalError(410, "Approval request has expired")
            elif row["status"] == "EXPIRED":
                error = ApprovalError(410, "Approval request has expired")
            else:
                cur = c.execute(
                    "UPDATE approvals SET status=?, decided_at=?, decided_by=?"
                    " WHERE id=? AND status='PENDING'",
                    (new_status, utc_now(), decided_by, approval_id))
                if cur.rowcount != 1:
                    error = ApprovalError(409, f"Approval request already processed ({row['status']})")
        if error:  # raised after the transaction is committed
            raise error
        return self._public(row)

    def finish(self, approval_id: str, status: str) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE approvals SET status=? WHERE id=? AND status='APPROVED'",
                      (status, approval_id))
