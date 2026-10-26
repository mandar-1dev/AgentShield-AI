import json
import time
from dataclasses import replace

import pytest
from pydantic import BaseModel

from app.container import build_container
from app.schemas import Decision, ExecutionStatus, Permission
from app.services.approvals import ApprovalError
from app.tools.registry import ToolSpec
from app.tools.safe_tools import NoArgs

REPORT = {"report_id": "RPT-001", "reason": "Quarterly audit review"}


def call(c, user, tool, args, rid="r1"):
    return c.gateway.authorize_and_execute(tool, args, user, rid)


def test_permitted_tool_executes(container, user):
    r = call(container, user, "get_public_status", {})
    assert r.decision is Decision.ALLOWED and r.execution_status is ExecutionStatus.EXECUTED
    assert r.result["status"] == "operational"


def test_search_returns_fictional_records(container, user):
    r = call(container, user, "search_demo_records", {"query": "research", "limit": 2})
    assert r.execution_status is ExecutionStatus.EXECUTED and r.result["count"] == 2


def test_unknown_tool_blocked(container, user):
    r = call(container, user, "delete_all_files", {"path": "/"})
    assert r.decision is Decision.BLOCKED and r.execution_status is ExecutionStatus.NOT_EXECUTED


@pytest.mark.parametrize("name", [None, "", "Get Status", "../etc/passwd", "a" * 200, 123])
def test_malformed_tool_names_blocked(container, user, name):
    assert call(container, user, name, {}).decision is Decision.BLOCKED


@pytest.mark.parametrize("args", [{"query": "x", "limit": 999}, {"query": ""}, {},
                                  {"query": "a; DROP TABLE"}, "not-a-dict", {"query": 5}])
def test_invalid_arguments_rejected(container, user, args):
    r = call(container, user, "search_demo_records", args)
    assert r.decision is Decision.BLOCKED and r.execution_status is ExecutionStatus.NOT_EXECUTED


def test_extra_arguments_rejected(container, user):
    r = call(container, user, "get_public_status", {"admin": True})
    assert r.decision is Decision.BLOCKED and "Extra" in r.reason


def test_restricted_action_blocked(container, user):
    r = call(container, user, "simulate_restricted_action", {"action": "wipe"})
    assert r.decision is Decision.BLOCKED and r.execution_status is ExecutionStatus.NOT_EXECUTED


def test_non_permitted_role_blocked(container):
    from app.schemas import UserContext
    r = call(container, UserContext(role="guest"), "get_public_status", {})
    assert r.decision is Decision.BLOCKED


def test_sensitive_request_creates_pending_approval(container, user):
    r = call(container, user, "request_sensitive_report", REPORT)
    assert r.decision is Decision.PENDING_APPROVAL and r.execution_status is ExecutionStatus.NOT_EXECUTED
    row = container.approvals.get(r.approval_id)
    assert row["status"] == "PENDING" and row["tool_name"] == "request_sensitive_report"
    assert row["arguments"] == REPORT and row["expires_at"] > row["created_at"]


def test_reject_prevents_execution(container, user):
    r = call(container, user, "request_sensitive_report", REPORT)
    out = container.gateway.decide_approval(r.approval_id, False, "admin", "r2")
    assert out.decision is Decision.REJECTED and out.execution_status is ExecutionStatus.NOT_EXECUTED
    with pytest.raises(ApprovalError) as e:
        container.gateway.decide_approval(r.approval_id, True, "admin", "r3")
    assert e.value.status_code == 409
    assert not [x for x in container.audit.list() if x["execution_status"] == "EXECUTED"]


def test_approve_executes_only_intended_operation(container, user):
    r = call(container, user, "request_sensitive_report", REPORT)
    out = container.gateway.decide_approval(r.approval_id, True, "admin", "r2")
    assert out.decision is Decision.APPROVED and out.execution_status is ExecutionStatus.EXECUTED
    assert out.tool_name == "request_sensitive_report" and out.result["report_id"] == "RPT-001"
    assert "content" not in json.dumps(out.result).replace("no report content", "")
    assert container.approvals.get(r.approval_id)["status"] == "EXECUTED"


def test_expired_approval_cannot_execute(settings, user):
    c = build_container(replace(settings, approval_ttl_seconds=0))
    r = call(c, user, "request_sensitive_report", REPORT)
    time.sleep(0.01)
    with pytest.raises(ApprovalError) as e:
        c.gateway.decide_approval(r.approval_id, True, "admin", "r2")
    assert e.value.status_code == 410
    assert c.approvals.get(r.approval_id)["status"] == "EXPIRED"
    assert not [x for x in c.audit.list() if x["execution_status"] == "EXECUTED"]


def test_replay_cannot_execute_twice(container, user):
    r = call(container, user, "request_sensitive_report", REPORT)
    container.gateway.decide_approval(r.approval_id, True, "admin", "r2")
    with pytest.raises(ApprovalError) as e:
        container.gateway.decide_approval(r.approval_id, True, "admin", "r3")
    assert e.value.status_code == 409
    executed = [x for x in container.audit.list() if x["execution_status"] == "EXECUTED"]
    assert len(executed) == 1


def test_unknown_approval_id(container):
    with pytest.raises(ApprovalError) as e:
        container.gateway.decide_approval("nope", True, "admin", "r")
    assert e.value.status_code == 404


def test_audit_records_created_for_decisions(container, user):
    call(container, user, "get_public_status", {})
    call(container, user, "nope", {})
    call(container, user, "request_sensitive_report", REPORT)
    decisions = {e["decision"] for e in container.audit.list()}
    assert {"ALLOWED", "BLOCKED", "PENDING_APPROVAL"} <= decisions
    e = container.audit.list(decision="BLOCKED")[0]
    assert e["request_id"] and e["timestamp"].endswith("Z") and e["reason"]


def test_secrets_not_in_audit(container, user):
    call(container, user, "search_demo_records", {"query": "x", "token": "SUPERSECRET123", "password": "hunter2"})
    call(container, user, "bad tool SUPERSECRET123", {"api_key": "SUPERSECRET123"})
    dump = json.dumps(container.audit.list())
    assert "SUPERSECRET123" not in dump and "hunter2" not in dump and "[REDACTED]" in dump


def test_tool_execution_failure_recorded(container, user):
    def boom(_):
        raise RuntimeError("internal path /secret/stuff")

    container.registry.register(ToolSpec("flaky_tool", "fails", NoArgs, BaseModel,
                                         Permission.PUBLIC, boom))
    r = call(container, user, "flaky_tool", {})
    assert r.decision is Decision.ALLOWED and r.execution_status is ExecutionStatus.FAILED
    assert "/secret/stuff" not in r.reason
    ev = container.audit.list(tool_name="flaky_tool")[0]
    assert ev["execution_status"] == "FAILED"
