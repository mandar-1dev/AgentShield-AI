"""Pydantic models shared by the API, gateway and agent."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class Decision(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class Permission(str, Enum):
    PUBLIC = "public"
    APPROVAL_REQUIRED = "approval_required"
    RESTRICTED = "restricted"


class UserContext(BaseModel):
    user_id: str = "demo-user"
    role: str = "user"


class GatewayResult(BaseModel):
    request_id: str
    tool_name: Optional[str] = None
    decision: Decision
    execution_status: ExecutionStatus = ExecutionStatus.NOT_EXECUTED
    reason: str
    result: Optional[dict[str, Any]] = None
    approval_id: Optional[str] = None
    duration_ms: float = 0.0


class AgentRunRequest(BaseModel):
    message: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    scenario: Optional[int] = Field(default=None, ge=1, le=7)

    @model_validator(mode="after")
    def _need_one(self):
        if self.message is None and self.scenario is None:
            raise ValueError("Provide either 'message' or 'scenario'")
        return self


class AgentToolCall(BaseModel):
    proposed_tool: str
    proposed_arguments: dict[str, Any]
    outcome: GatewayResult


class AgentRunResponse(BaseModel):
    request_id: str
    mode: str  # "demo" or "ollama"
    source: str  # "demo_engine" or "ollama:<model>"
    status: str  # "COMPLETED" or "ERROR"
    final_message: Optional[str] = None
    error_code: Optional[str] = None
    tool_calls: list[AgentToolCall] = []
