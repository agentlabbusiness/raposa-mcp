"""R6 — contract tests for the raposa-mcp server. Spec: raposa/docs/specs/R6-mcp-server.md

Written before the implementation. The Raposa API is faked with an httpx
MockTransport; the MCP side is exercised through the SDK's in-memory
client/server session, i.e. exactly what a real MCP client would see.
"""
import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session

from raposa_mcp import server as srv


class FakeApi:
    """Minimal Raposa API: create → pending; decided after `decide_after` reads."""

    def __init__(self, decide_after=1, final="approved", status_code=200):
        self.decide_after, self.final, self.status_code = decide_after, final, status_code
        self.reads, self.calls, self.auth = 0, [], []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        self.auth.append(request.headers.get("authorization"))
        if self.status_code != 200:
            return httpx.Response(self.status_code, json={"detail": f"faked {self.status_code}"})
        if request.method == "POST" and request.url.path.endswith("/v1/approvals"):
            body = json.loads(request.content)
            assert body["risk"] in ("low", "medium", "high")
            return httpx.Response(200, json={"id": "ap-1", "status": "pending"})
        if request.method == "GET" and "/v1/approvals/ap-1" in request.url.path:
            self.reads += 1
            decided = self.reads >= self.decide_after
            return httpx.Response(200, json={
                "id": "ap-1", "action": "payout", "status": self.final if decided else "pending",
                "decided_by": "approver:finance-lead" if decided else "",
                "decided_at": "2026-09-03T10:00:00.000000Z" if decided else None,
                "decision_comment": "ok" if decided else None})
        return httpx.Response(404, json={"detail": "no"})


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setenv("RAPOSA_API_KEY", "test-key-value")
    monkeypatch.setattr(srv, "POLL_SEC", 0)          # no real sleeping in tests
    srv.configure(transport=httpx.MockTransport(fake.handler))
    return fake


async def _call(name, args):
    async with client_session(srv.mcp._mcp_server) as client:
        return await client.call_tool(name, args)


def _payload(result):
    text = "".join(c.text for c in result.content if getattr(c, "text", None))
    try:
        return json.loads(text)
    except ValueError:
        return {"_text": text}


async def test_tools_are_listed_with_schemas(api):
    async with client_session(srv.mcp._mcp_server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) >= {"request_human_approval", "create_approval", "get_approval"}
    props = tools["request_human_approval"].inputSchema["properties"]
    assert {"action", "context", "risk"} <= set(props)
    assert "api_key" not in props and "key" not in props


async def test_request_waits_and_returns_approved(api):
    api.decide_after = 3
    r = await _call("request_human_approval",
                    {"action": "payout", "context": "invoice 7", "risk": "high", "wait_sec": 30})
    out = _payload(r)
    assert out["status"] == "approved" and out["approved"] is True
    assert out["decided_by"] == "approver:finance-lead" and out["id"] == "ap-1"
    assert api.reads == 3


async def test_reject_is_not_approved(api):
    api.final = "rejected"
    out = _payload(await _call("request_human_approval",
                               {"action": "payout", "context": "x", "risk": "low"}))
    assert out["status"] == "rejected" and out["approved"] is False


async def test_timeout_is_not_approval(api):
    api.decide_after = 10 ** 6
    out = _payload(await _call("request_human_approval",
                               {"action": "payout", "context": "x", "risk": "low", "wait_sec": 0}))
    assert out["status"] == "timeout" and out["approved"] is False
    assert "not approved" in out["message"].lower()


async def test_expired_is_not_approval(api):
    api.final = "expired"
    out = _payload(await _call("request_human_approval",
                               {"action": "payout", "context": "x", "risk": "low"}))
    assert out["status"] == "expired" and out["approved"] is False


async def test_create_returns_id_without_waiting(api):
    out = _payload(await _call("create_approval", {"action": "deploy", "context": "v2", "risk": "medium"}))
    assert out == {"id": "ap-1", "status": "pending"}
    assert api.reads == 0


async def test_get_approval(api):
    api.decide_after = 1
    out = _payload(await _call("get_approval", {"approval_id": "ap-1"}))
    assert out["status"] == "approved" and out["approved"] is True


async def test_api_error_is_reported_not_swallowed(api):
    api.status_code = 401
    r = await _call("create_approval", {"action": "x", "context": "y", "risk": "low"})
    assert r.isError
    assert "401" in _payload(r).get("_text", "")


async def test_bad_risk_never_hits_the_api(api):
    r = await _call("create_approval", {"action": "x", "context": "y", "risk": "critical"})
    assert r.isError and api.calls == []


async def test_missing_key_is_a_clear_error_and_server_still_lists_tools(monkeypatch):
    monkeypatch.delenv("RAPOSA_API_KEY", raising=False)
    srv.configure(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    async with client_session(srv.mcp._mcp_server) as client:
        assert (await client.list_tools()).tools
        r = await client.call_tool("create_approval", {"action": "x", "context": "y", "risk": "low"})
    assert r.isError and "RAPOSA_API_KEY" in _payload(r).get("_text", "")


async def test_key_is_sent_as_bearer_and_never_returned(api):
    r = await _call("create_approval", {"action": "x", "context": "y", "risk": "low"})
    assert api.auth[-1] == "Bearer test-key-value"
    assert "test-key-value" not in json.dumps(_payload(r))
