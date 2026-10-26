from tests.conftest import ADMIN


def run(client, scenario):
    return client.post("/api/agent/run", json={"scenario": scenario})


def test_health_and_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "up" and r.json()["mode"] == "demo"
    assert r.headers["X-Request-ID"] == r.json()["request_id"]


def test_tools_listing(client):
    names = {t["name"]: t for t in client.get("/api/tools").json()}
    assert len(names) == 5 and names["simulate_restricted_action"]["availability"] == "blocked"
    assert names["request_sensitive_report"]["availability"] == "requires_approval"


def test_all_scenarios_are_deterministic(client):
    expected = {1: "ALLOWED", 2: "ALLOWED", 3: "BLOCKED", 4: "BLOCKED", 5: "PENDING_APPROVAL", 6: "BLOCKED"}
    for n, dec in expected.items():
        for _ in range(2):
            body = run(client, n).json()
            assert body["source"] == "demo_engine" and body["mode"] == "demo"
            assert body["tool_calls"][0]["outcome"]["decision"] == dec


def test_scenario_7_safe_error(client):
    r = run(client, 7)
    assert r.status_code == 200 and r.json()["status"] == "ERROR"
    assert r.json()["error_code"] == "SIMULATED_MODEL_FAILURE" and r.json()["tool_calls"] == []


def test_request_validation(client):
    assert client.post("/api/agent/run", json={}).status_code == 422
    assert client.post("/api/agent/run", json={"scenario": 99}).status_code == 422


def test_free_text_demo(client):
    body = client.post("/api/agent/run", json={"message": "what is the status?"}).json()
    assert body["tool_calls"][0]["proposed_tool"] == "get_public_status"


def test_approval_endpoints_require_admin(client):
    aid = run(client, 5).json()["tool_calls"][0]["outcome"]["approval_id"]
    assert client.get("/api/approvals").status_code == 401
    assert client.post(f"/api/approvals/{aid}/approve").status_code == 401
    assert client.post(f"/api/approvals/{aid}/reject").status_code == 401
    bad = {"X-Admin-Token": "wrong"}
    assert client.post(f"/api/approvals/{aid}/approve", headers=bad).status_code == 401
    assert client.get("/api/approvals", headers=ADMIN).status_code == 200


def test_admin_disabled_when_no_token_configured(settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import create_app
    c = TestClient(create_app(replace(settings, admin_token="")))
    assert c.get("/api/approvals", headers={"X-Admin-Token": ""}).status_code == 401


def test_approve_flow_and_replay(client):
    aid = run(client, 5).json()["tool_calls"][0]["outcome"]["approval_id"]
    ok = client.post(f"/api/approvals/{aid}/approve", headers=ADMIN)
    assert ok.status_code == 200 and ok.json()["execution_status"] == "EXECUTED"
    assert client.post(f"/api/approvals/{aid}/approve", headers=ADMIN).status_code == 409
    assert client.post(f"/api/approvals/{aid}/reject", headers=ADMIN).status_code == 409


def test_reject_flow(client):
    aid = run(client, 5).json()["tool_calls"][0]["outcome"]["approval_id"]
    r = client.post(f"/api/approvals/{aid}/reject", headers=ADMIN)
    assert r.json()["decision"] == "REJECTED" and r.json()["execution_status"] == "NOT_EXECUTED"


def test_unknown_approval_404(client):
    assert client.post("/api/approvals/unknown/approve", headers=ADMIN).status_code == 404


def test_audit_filters_and_limit(client):
    for n in (1, 3, 6):
        run(client, n)
    ev = client.get("/api/audit", params={"decision": "BLOCKED"}).json()["events"]
    assert ev and all(e["decision"] == "BLOCKED" for e in ev)
    ev = client.get("/api/audit", params={"tool": "get_public_status"}).json()["events"]
    assert ev and all(e["tool_name"] == "get_public_status" for e in ev)
    assert len(client.get("/api/audit", params={"limit": 1}).json()["events"]) == 1
    assert client.get("/api/audit", params={"limit": 5000}).status_code == 422


def test_sql_injection_in_filter_is_harmless(client):
    r = client.get("/api/audit", params={"tool": "x' OR '1'='1"})
    assert r.status_code == 200 and r.json()["events"] == []


def test_metrics(client):
    run(client, 1); run(client, 3); run(client, 5)
    m = client.get("/api/metrics").json()
    assert m["total_requests"] == 3 and m["allowed"] == 1 and m["blocked"] == 1
    assert m["pending_approvals"] == 1 and m["failed_executions"] == 0


def test_no_secrets_in_responses(client):
    for path in ("/health", "/api/tools", "/api/audit", "/api/metrics"):
        assert "test-admin-token" not in client.get(path).text


def test_error_responses_do_not_leak(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404 and "Traceback" not in r.text and "request_id" in r.json()


def test_ollama_down_returns_503_not_crash(settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import create_app
    s = replace(settings, demo_mode=False, ollama_base_url="http://127.0.0.1:9", ollama_timeout=2)
    c = TestClient(create_app(s))
    r = c.post("/api/agent/run", json={"message": "hello"})
    assert r.status_code == 503 and r.json()["error_code"] == "MODEL_UNAVAILABLE"
    assert c.get("/health/ollama").json()["reachable"] is False
    assert c.get("/health").status_code == 200
