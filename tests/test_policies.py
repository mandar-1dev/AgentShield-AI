from app.schemas import Decision, Permission, UserContext
from app.security.policies import PolicyEngine
from app.tools.safe_tools import build_default_registry

REG = build_default_registry()
U = UserContext()


def test_unknown_tool_denied_by_default():
    assert PolicyEngine().evaluate(None, U).decision is Decision.BLOCKED


def test_permission_mapping():
    p = PolicyEngine()
    assert p.evaluate(REG.get("get_public_status"), U).decision is Decision.ALLOWED
    assert p.evaluate(REG.get("request_sensitive_report"), U).decision is Decision.PENDING_APPROVAL
    assert p.evaluate(REG.get("simulate_restricted_action"), U).decision is Decision.BLOCKED


def test_override_can_tighten_policy():
    p = PolicyEngine({"get_system_health": "restricted"})
    assert p.evaluate(REG.get("get_system_health"), U).decision is Decision.BLOCKED


def test_unclassified_permission_denied():
    p = PolicyEngine({"get_system_health": "wide_open"})
    assert p.evaluate(REG.get("get_system_health"), U).decision is Decision.BLOCKED


def test_unknown_role_denied():
    assert PolicyEngine().evaluate(REG.get("get_public_status"), UserContext(role="guest")).decision is Decision.BLOCKED


def test_all_default_tools_classified():
    assert {t.permission for t in REG.list()} == set(Permission)
