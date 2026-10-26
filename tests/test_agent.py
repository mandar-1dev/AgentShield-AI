from dataclasses import replace

import httpx
import pytest

from app.agent.ollama_client import OllamaBadResponse, OllamaClient, OllamaUnavailable
from app.container import build_container
from app.schemas import UserContext

U = UserContext()


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def chat(self, messages, tools):
        self.calls += 1
        r = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    def health(self):
        return {"reachable": True}


def tool_msg(name, args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def real_agent(settings, fake):
    return build_container(replace(settings, demo_mode=False), fake).agent


def test_ollama_unavailable_fails_safely(settings):
    r = real_agent(settings, FakeClient(OllamaUnavailable("down"))).run("hi", None, U, "r")
    assert r.status == "ERROR" and r.error_code == "MODEL_UNAVAILABLE" and r.tool_calls == []


def test_malformed_model_output_handled(settings):
    for bad in (OllamaBadResponse("junk"), "garbage", {"tool_calls": "oops"}, {"tool_calls": 5}):
        r = real_agent(settings, FakeClient(bad)).run("hi", None, U, "r")
        assert r.status == "ERROR" and r.error_code in ("MODEL_BAD_RESPONSE",)


def test_malformed_tool_call_items_are_blocked(settings):
    msg = {"content": "", "tool_calls": [None, {"function": "x"}, {"function": {"name": 7, "arguments": "{bad"}}]}
    r = real_agent(settings, FakeClient(msg, {"content": "done"})).run("hi", None, U, "r")
    assert r.status == "COMPLETED" and all(t.outcome.decision.value == "BLOCKED" for t in r.tool_calls)


def test_loop_stops_at_maximum(settings):
    fake = FakeClient(tool_msg("get_public_status", {}))
    r = real_agent(settings, fake).run("loop", None, U, "r")
    assert fake.calls == 5 and r.error_code == "MAX_ITERATIONS_REACHED"
    assert len(r.tool_calls) == 5


def test_model_proposing_unsafe_calls_is_blocked(settings):
    fake = FakeClient(tool_msg("rm_rf", {"path": "/"}), tool_msg("simulate_restricted_action", {"action": "x"}),
                      {"content": "Sorry, I could not do that."})
    c = build_container(replace(settings, demo_mode=False), fake)
    r = c.agent.run("do bad things", None, U, "r")
    assert [t.outcome.decision.value for t in r.tool_calls] == ["BLOCKED", "BLOCKED"]
    assert r.status == "COMPLETED" and r.source.startswith("ollama:")
    assert not [e for e in c.audit.list() if e["execution_status"] == "EXECUTED"]


def test_valid_model_call_goes_through_gateway_and_json_string_args(settings):
    fake = FakeClient(tool_msg("search_demo_records", '{"query": "research", "limit": 2}'), {"content": "Found 2."})
    c = build_container(replace(settings, demo_mode=False), fake)
    r = c.agent.run("find research", None, U, "r")
    assert r.tool_calls[0].outcome.result["count"] == 2 and r.final_message == "Found 2."
    assert c.audit.list(tool_name="search_demo_records")


def test_secrets_not_sent_to_model(settings):
    seen = []

    class Spy(FakeClient):
        def chat(self, messages, tools):
            seen.append(str(messages) + str(tools))
            return {"content": "ok"}

    real_agent(replace(settings, admin_token="TOPSECRET"), Spy()).run("hi", None, U, "r")
    assert "TOPSECRET" not in "".join(seen)


def test_demo_mode_deterministic(container):
    a = container.agent.run(None, 5, U, "r1")
    b = container.agent.run(None, 5, U, "r2")
    assert a.source == b.source == "demo_engine"
    assert a.tool_calls[0].outcome.decision == b.tool_calls[0].outcome.decision


def test_real_client_bad_json_and_connect_error():
    ok = lambda h: OllamaClient("http://x", "m", 2, transport=httpx.MockTransport(h))
    with pytest.raises(OllamaBadResponse):
        ok(lambda r: httpx.Response(200, content=b"not json")).chat([], [])
    with pytest.raises(OllamaBadResponse):
        ok(lambda r: httpx.Response(200, json={"nomessage": 1})).chat([], [])
    with pytest.raises(OllamaUnavailable):
        ok(lambda r: httpx.Response(404)).chat([], [])
    with pytest.raises(OllamaUnavailable):
        def boom(r): raise httpx.ConnectError("refused")
        ok(boom).chat([], [])
    with pytest.raises(OllamaUnavailable):
        def slow(r): raise httpx.ReadTimeout("slow")
        ok(slow).chat([], [])


def test_real_client_health():
    h = lambda r: httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})
    assert OllamaClient("http://x", "llama3.1:8b", 2, transport=httpx.MockTransport(h)).health()["model_available"]
