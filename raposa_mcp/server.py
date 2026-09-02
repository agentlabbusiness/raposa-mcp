"""raposa-mcp — an MCP server that gives an agent one honest tool: ask a human.

    request_human_approval(action, context, risk) -> {approved: bool, ...}

`approved` is True only when a named human approved. A timeout, an expiry or
a rejection all come back with approved=False — silence is not consent.
The API key lives in RAPOSA_API_KEY and is never part of tool inputs or
outputs. Spec: raposa/docs/specs/R6-mcp-server.md
"""
import asyncio
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE = "https://dcescrypt.com/api"
POLL_SEC = 5.0
RISKS = ("low", "medium", "high")

mcp = FastMCP(
    "raposa",
    instructions=("Raposa Aval: pause a high-stakes action until an authorised human approves it. "
                  "Call request_human_approval before payments, deploys, deletions or customer-facing "
                  "commitments. Proceed only when the result has approved=true."),
)

_transport = None   # tests inject an httpx.MockTransport


def configure(transport=None):
    global _transport
    _transport = transport


class ToolError(Exception):
    pass


def _client() -> httpx.AsyncClient:
    key = os.environ.get("RAPOSA_API_KEY", "").strip()
    if not key:
        raise ToolError("RAPOSA_API_KEY is not set. Get a free sandbox key at https://raposa.group/start/ "
                        "and put it in the MCP server's environment.")
    base = os.environ.get("RAPOSA_API_BASE", DEFAULT_BASE).rstrip("/")
    return httpx.AsyncClient(base_url=base, transport=_transport, timeout=20.0,
                             headers={"Authorization": f"Bearer {key}",
                                      "User-Agent": "raposa-mcp/0.1 (+https://raposa.group)"})


async def _request(method: str, path: str, **kw) -> dict:
    async with _client() as c:
        r = await c.request(method, path, **kw)
        if r.status_code == 429:
            await asyncio.sleep(min(float(r.headers.get("Retry-After", "1") or 1), 10))
            r = await c.request(method, path, **kw)
        if r.status_code >= 400:
            raise ToolError(f"Raposa API {r.status_code} on {method} {path}: {r.text[:300]}")
        return r.json()


def _shape(a: dict) -> dict:
    status = a.get("status")
    return {"id": a.get("id"), "status": status, "approved": status == "approved",
            "decided_by": a.get("decided_by") or None, "decided_at": a.get("decided_at"),
            "comment": a.get("decision_comment"),
            "message": {"approved": "Approved by a human — proceed.",
                        "rejected": "Rejected by a human — do not proceed.",
                        "expired": "Not approved — the request expired before anyone decided.",
                        "pending": "Still waiting for a human."}.get(status, "Not approved.")}


def _validate(action: str, context: str, risk: str):
    if risk not in RISKS:
        raise ToolError(f"risk must be one of {RISKS}, got {risk!r}")
    if not action or not context:
        raise ToolError("action and context are required")


def _create_body(action, context, risk, requested_by, expires_in_sec, webhook_url):
    body = {"action": action[:200], "context": context[:4000], "risk": risk,
            "requested_by": (requested_by or "mcp-agent")[:200]}
    if expires_in_sec:
        body["expires_in_sec"] = int(expires_in_sec)
    if webhook_url:
        body["webhook_url"] = webhook_url
    return body


@mcp.tool()
async def create_approval(action: str, context: str, risk: str, requested_by: str = "mcp-agent",
                          expires_in_sec: int | None = None, webhook_url: str | None = None) -> str:
    """Create an approval request and return its id immediately (no waiting).
    Use with a webhook_url, or poll with get_approval. risk: low | medium | high."""
    try:
        _validate(action, context, risk)
        out = await _request("POST", "/v1/approvals",
                             json=_create_body(action, context, risk, requested_by, expires_in_sec, webhook_url))
        return json.dumps({"id": out.get("id"), "status": out.get("status")})
    except ToolError as exc:
        raise RuntimeError(str(exc))


@mcp.tool()
async def get_approval(approval_id: str) -> str:
    """Read an approval by id. Look at `approved` — it is true only when a human approved."""
    try:
        return json.dumps(_shape(await _request("GET", f"/v1/approvals/{approval_id}")))
    except ToolError as exc:
        raise RuntimeError(str(exc))


@mcp.tool()
async def request_human_approval(action: str, context: str, risk: str, requested_by: str = "mcp-agent",
                                 wait_sec: int = 600, expires_in_sec: int | None = None) -> str:
    """Ask an authorised human to approve an action and wait for the answer.
    Returns {approved: bool, status, decided_by, ...}. Proceed ONLY if approved is true —
    a timeout, an expiry or a rejection means do not proceed. risk: low | medium | high."""
    try:
        _validate(action, context, risk)
        created = await _request("POST", "/v1/approvals",
                                 json=_create_body(action, context, risk, requested_by, expires_in_sec, None))
        aid = created.get("id")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(0, int(wait_sec))
        while True:
            a = await _request("GET", f"/v1/approvals/{aid}")
            if a.get("status") != "pending":
                return json.dumps(_shape(a))
            if loop.time() >= deadline:
                return json.dumps({"id": aid, "status": "timeout", "approved": False,
                                   "decided_by": None, "decided_at": None, "comment": None,
                                   "message": f"Not approved — nobody answered in {wait_sec}s. "
                                              "The request is still open; check later with get_approval."})
            await asyncio.sleep(POLL_SEC)
    except ToolError as exc:
        raise RuntimeError(str(exc))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
