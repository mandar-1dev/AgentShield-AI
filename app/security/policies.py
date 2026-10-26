"""Policy engine: maps a tool's permission class to a decision. Default = deny."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas import Decision, Permission, UserContext
from app.tools.registry import ToolSpec


@dataclass
class PolicyDecision:
    decision: Decision
    reason: str


class PolicyEngine:
    def __init__(self, overrides: Optional[dict] = None,
                 allowed_roles: tuple[str, ...] = ("user", "admin")):
        self.overrides = dict(overrides or {})
        self.allowed_roles = allowed_roles

    def effective_permission(self, spec: ToolSpec):
        raw = self.overrides.get(spec.name, spec.permission)
        try:
            return Permission(raw)
        except ValueError:
            return None  # unclassified -> deny

    def evaluate(self, spec: Optional[ToolSpec], user: UserContext) -> PolicyDecision:
        if spec is None:
            return PolicyDecision(Decision.BLOCKED, "Unknown tool - default deny")
        perm = self.effective_permission(spec)
        if perm is None:
            return PolicyDecision(Decision.BLOCKED, "Tool has no valid permission class - default deny")
        if user.role not in self.allowed_roles:
            return PolicyDecision(Decision.BLOCKED, f"Role '{user.role[:20]}' is not permitted to use tools")
        if perm is Permission.PUBLIC:
            return PolicyDecision(Decision.ALLOWED, "Public tool permitted by policy")
        if perm is Permission.APPROVAL_REQUIRED:
            return PolicyDecision(Decision.PENDING_APPROVAL, "Sensitive tool requires human approval")
        return PolicyDecision(Decision.BLOCKED, "Restricted tool is blocked by policy")
