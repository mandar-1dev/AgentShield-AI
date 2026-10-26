"""The security gateway: the ONLY path from a proposed tool call to execution."""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from app.schemas import Decision, ExecutionStatus, GatewayResult, UserContext
from app.security.policies import PolicyEngine
from app.security.validators import (ValidationFailure, safe_tool_label,
                                     validate_arguments, validate_tool_name)
from app.services.approvals import ApprovalError, ApprovalService
from app.services.audit import AuditService
from app.tools.registry import ToolRegistry, ToolSpec


class SecurityGateway:
    def __init__(self, registry: ToolRegistry, policy: PolicyEngine,
                 audit: AuditService, approvals: ApprovalService):
        self.registry = registry
        self.policy = policy
        self.audit = audit
        self.approvals = approvals

    # ---------- helpers ----------
    def _done(self, *, start: float, request_id: str, tool_name: Any, decision: Decision,
              status: ExecutionStatus, reason: str, arguments: Any, result=None,
              approval_id=None, actor=None) -> GatewayResult:
        duration = round((time.perf_counter() - start) * 1000, 2)
        self.audit.record(request_id=request_id, tool_name=tool_name, decision=decision.value,
                          execution_status=status.value, reason=reason, arguments=arguments,
                          duration_ms=duration, actor=actor)
        return GatewayResult(request_id=request_id, tool_name=safe_tool_label(tool_name),
                             decision=decision, execution_status=status, reason=reason,
                             result=result, approval_id=approval_id, duration_ms=duration)

    @staticmethod
    def _run(spec: ToolSpec, parsed: BaseModel):
        """Execute a registered python callable. Authorization has already happened."""
        try:
            raw = spec.func(parsed)
            data = raw.model_dump() if isinstance(raw, BaseModel) else raw
            result = spec.result_model.model_validate(data).model_dump()
            return ExecutionStatus.EXECUTED, result, "Tool executed successfully"
        except Exception as exc:  # message deliberately not leaked
            return ExecutionStatus.FAILED, None, f"Tool execution failed ({type(exc).__name__})"

    # ---------- main entry point ----------
    def authorize_and_execute(self, tool_name: Any, arguments: Any, user_context: UserContext,
                              request_id: str) -> GatewayResult:
        start = time.perf_counter()
        N = ExecutionStatus.NOT_EXECUTED

        def block(reason: str) -> GatewayResult:
            return self._done(start=start, request_id=request_id, tool_name=tool_name,
                              decision=Decision.BLOCKED, status=N, reason=reason,
                              arguments=arguments, actor=user_context.user_id)

        # 1-2. tool name must be well-formed and in the allowlist
        try:
            name = validate_tool_name(tool_name)
        except ValidationFailure as e:
            return block(e.reason)
        spec = self.registry.get(name)
        if spec is None:
            return block("Unknown tool - not in registry allowlist")

        # 3-4. strict argument validation (types, ranges, no extra fields)
        try:
            parsed = validate_arguments(spec, arguments)
        except ValidationFailure as e:
            return block(e.reason)

        # 5-6. policy
        verdict = self.policy.evaluate(spec, user_context)
        if verdict.decision is Decision.BLOCKED:
            return block(verdict.reason)

        # 7. human approval: store the *validated* arguments, do not execute
        if verdict.decision is Decision.PENDING_APPROVAL:
            approval_id = self.approvals.create(request_id, name, parsed.model_dump())
            return self._done(start=start, request_id=request_id, tool_name=name,
                              decision=Decision.PENDING_APPROVAL, status=N,
                              reason=verdict.reason, arguments=parsed.model_dump(),
                              approval_id=approval_id, actor=user_context.user_id)

        # 8-9. authorized -> execute -> audit
        status, result, reason = self._run(spec, parsed)
        return self._done(start=start, request_id=request_id, tool_name=name,
                          decision=Decision.ALLOWED, status=status, reason=reason,
                          arguments=parsed.model_dump(), result=result,
                          actor=user_context.user_id)

    # ---------- approval decisions ----------
    def decide_approval(self, approval_id: str, approve: bool, admin_id: str,
                        request_id: str) -> GatewayResult:
        start = time.perf_counter()
        N = ExecutionStatus.NOT_EXECUTED
        existing = self.approvals.get(approval_id)
        tool_for_log = existing["tool_name"] if existing else None
        try:
            row = self.approvals.claim(approval_id, "APPROVED" if approve else "REJECTED", admin_id)
        except ApprovalError as e:
            self._done(start=start, request_id=request_id, tool_name=tool_for_log,
                       decision=Decision.EXPIRED if e.status_code == 410 else Decision.BLOCKED,
                       status=N, reason=f"Approval not processed: {e.message}",
                       arguments={"approval_id": approval_id[:40]}, actor=admin_id)
            raise

        if not approve:
            return self._done(start=start, request_id=request_id, tool_name=row["tool_name"],
                              decision=Decision.REJECTED, status=N,
                              reason="Rejected by administrator; nothing executed",
                              arguments=row["arguments"], approval_id=approval_id, actor=admin_id)

        # Execute exactly the stored, previously validated request - re-checked defensively.
        spec = self.registry.get(row["tool_name"])
        if spec is None:
            self.approvals.finish(approval_id, "FAILED")
            return self._done(start=start, request_id=request_id, tool_name=row["tool_name"],
                              decision=Decision.BLOCKED, status=N,
                              reason="Tool no longer registered", arguments=row["arguments"],
                              approval_id=approval_id, actor=admin_id)
        try:
            parsed = validate_arguments(spec, self.approvals.get_raw_arguments(approval_id))
        except ValidationFailure as e:
            self.approvals.finish(approval_id, "FAILED")
            return self._done(start=start, request_id=request_id, tool_name=spec.name,
                              decision=Decision.BLOCKED, status=N, reason=e.reason,
                              arguments=row["arguments"], approval_id=approval_id, actor=admin_id)
        verdict = self.policy.evaluate(spec, UserContext(user_id=admin_id, role="admin"))
        if verdict.decision is Decision.BLOCKED:
            self.approvals.finish(approval_id, "FAILED")
            return self._done(start=start, request_id=request_id, tool_name=spec.name,
                              decision=Decision.BLOCKED, status=N,
                              reason=f"Policy changed since request: {verdict.reason}",
                              arguments=row["arguments"], approval_id=approval_id, actor=admin_id)

        status, result, reason = self._run(spec, parsed)
        self.approvals.finish(approval_id, "EXECUTED" if status is ExecutionStatus.EXECUTED else "FAILED")
        return self._done(start=start, request_id=request_id, tool_name=spec.name,
                          decision=Decision.APPROVED, status=status,
                          reason=f"Approved by administrator. {reason}", arguments=row["arguments"],
                          result=result, approval_id=approval_id, actor=admin_id)
