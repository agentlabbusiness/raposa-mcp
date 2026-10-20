# raposa-mcp

[![Raposa Aval — human approval MCP on mcprush](https://mcprush.com/badge/darius-ceponas-raposa-aval-human-approval-mcp/score.svg)](https://mcprush.com/darius-ceponas/raposa-aval-human-approval-mcp)

**Raposa Aval** is a human-approval MCP server by DC ESCRYPT (https://raposa.group).
It gives an agent one honest capability: before a high-stakes action runs, a named human
must explicitly approve it. The API is served from EU infrastructure; approvals are sealed
in a hash-chained audit log that can be exported for an auditor.

https://dcescrypt.com · [Documentation](https://raposa.group/docs/) · [Get a sandbox key](https://raposa.group/start/)

<!-- mcp-name: group.raposa/raposa-mcp -->

## 1 · Why fail-closed approval matters

`request_human_approval(action, context, risk)` returns:

```
{approved: true|false, decided_by, decided_at, comment, status, …}
```

`approved` is `true` **only when an authorised human pressed Approve**. Every other outcome —
a rejection, an expiry, a timeout — returns `approved: false`. Silence is never consent:

| Outcome | `approved` | Meaning |
|---|---|---|
| `approved` | `true` | A named human approved within the deadline |
| `rejected` | `false` | A named human rejected — do not proceed |
| `expired` | `false` | The TTL elapsed with no decision — do not proceed; no decision will arrive for the id |
| `timeout` | `false` | Nobody answered within `wait_sec` — the request stays open until its TTL; check later with `get_approval` |

The agent must branch on `approved`; the tool result never leaks a key or a secret.
A decided approval is final: a second decision on the same id is refused with HTTP 409.
Every decision lands in the hash-chained audit log (`/v1/audit/verify`, `/v1/audit/export`).

## 2 · Architecture

```
Agent ──tool call──▶ MCP server (raposa-mcp) ──HTTPS, Bearer RAPOSA_API_KEY──▶ Raposa Aval API
                                                                             │
                                                          approval created (status: pending)
                                                                             │
                     human sees it: e-mail link · web console · Slack · Telegram
                                                                             │
     agent ◀── polls get_approval / webhook callback ◀── decision (approve|reject)
```

* The MCP server holds only the client API key. It reads `RAPOSA_API_KEY` from its environment
  and never includes it in tool inputs or outputs.
* Approvals are scoped per API key: one customer can never read or decide another customer's
  requests — foreign ids answer `404 Approval not found`, and only an operator key can decide.
* Decisions carry the approver identity and a comment; re-deciding is refused.

## 3 · Getting an API key

1. Register a free sandbox at https://raposa.group/start/ (100 approvals a month).
2. An e-mail titled **“Raposa — your sandbox key”** arrives with a **one-time claim
   link, valid 24 hours**. The link shows the key once and cannot be reused; an expired
   or used link refuses with `410 gone`.
3. The claim link is itself the credential: whoever opens it first within 24 h owns the
   key. Treat that mail as a secret — do not forward it or paste the link into tickets
   and chats. If the link may have leaked before you opened it, write to
   contact@raposa.group: an unclaimed link self-expires in 24 h and a claimed key can be
   revoked and reissued from the account page or by support.
4. Put the key into the MCP server’s environment (below).

No production data is needed for the sandbox; the same flow issues paid-plan keys automatically
after checkout.

## 4 · Install (secure, step by step)

The server is a stdio MCP server, one command: `uvx raposa-mcp` (pin `raposa-mcp==0.1.2` to
freeze a published release).

### 4.1 The key never travels through a command line

Do not write `RAPOSA_API_KEY=<value>` into a chat, a shell command, a screenshot or a repository.
Two supported ways to bring the secret to the MCP process:

**Secret-manager export (1Password CLI, any similar tool works the same way):**

```bash
# ~/.zshrc or ~/.bash_profile — resolved at login from your own vault
export RAPOSA_API_KEY="$(op read 'op://Dev-API/<your-item>/key')"
```

The expansion happens inside the shell that starts your MCP client; the key never appears as a
literal argument (it would otherwise show in `ps`, in the shell history and in crash logs).

**Plain-environment alternative:** keep the value in a file with restrictive permissions and
`source` it from your shell profile. Whatever the source, the constant rule is: the MCP process
must inherit the variable from its parent environment, not receive it as an argument.

### 4.2 Claude Code

Claude Code supports `${VAR}` expansion in MCP configuration — the placeholder is stored in the
config file, resolved from the environment when the server starts ([MCP docs](https://code.claude.com/docs/en/mcp)):

```bash
claude mcp add raposa -e RAPOSA_API_KEY='${RAPOSA_API_KEY}' -- uvx raposa-mcp
claude mcp get raposa    # shows the ${...} reference — never the secret itself
```

Single quotes matter: without them the shell resolves the placeholder before Claude Code stores
it. `claude mcp get raposa` is the check that no secret landed in the configuration.

### 4.3 Generic MCP stdio config (`.mcp.json`, other clients)

```json
{
  "mcpServers": {
    "raposa": {
      "command": "uvx",
      "args": ["raposa-mcp"],
      "env": { "RAPOSA_API_KEY": "${RAPOSA_API_KEY}" }
    }
  }
}
```

### 4.4 Check it without spending the secret

```bash
# 1 · the stored placeholder is a reference, never the value:
claude mcp get raposa | grep -F '${RAPOSA_API_KEY}'     # prints the line — good
claude mcp get raposa | grep -F '<the key>'             # prints nothing — good
# 2 · end to end: list the tools (the server only runs when it can read the key):
#     three tools — create_approval, get_approval, request_human_approval
# 3 · a controlled read of a non-existent id must answer a 404 "Approval not
#     found", never a missing-environment error — that proves the key arrived
```

## 5 · Tools reference

All three tools take exactly these arguments (limits enforced client- and server-side):

### create_approval

Create an approval request and return its id immediately (no waiting). Use with a
`webhook_url`, or poll with `get_approval`.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `action` | string | yes | ≤ 200 chars |
| `context` | string | yes | ≤ 4000 chars |
| `risk` | string | yes | `low` \| `medium` \| `high` |
| `requested_by` | string | no | ≤ 200 chars, default `mcp-agent` |
| `expires_in_sec` | integer | no | 60–2592000 (default 86400 = 24 h) |
| `webhook_url` | string (URL) | no | where the signed decision callback is POSTed |

Returns `{"id": "…", "status": "pending"}`.

### get_approval

| Parameter | Type | Required |
|---|---|---|
| `approval_id` | string (UUID) | yes |

Returns the same shape for every terminal state:

```text
{"id": "…", "status": "approved|rejected|expired|pending", "approved": true|false,
 "decided_by": "…", "decided_at": "…", "comment": "…", "message": "…"}
```

`approved` is `true` only when `status == "approved"`.

### request_human_approval

Same parameters as `create_approval` (no `webhook_url`), plus:

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `wait_sec` | integer | no | how long to poll (5 s cadence), default 600 |

On a human decision returns the same shape as `get_approval`. On the deadline it returns
`{"status": "timeout", "approved": false, "id": "…", "message": "Not approved — nobody
answered in Ns. The request is still open; check later with get_approval."}` — and it really
stays open until its TTL: decide late via your console or `get_approval` later.

## 6 · Worked examples

Real outputs (sandbox, `uvx raposa-mcp==0.1.2`):

create_approval → returns immediately:

```json
{"id": "79d647c1-…", "status": "pending"}
```

get_approval while pending:

```json
{"id": "79d647c1-…", "status": "pending", "approved": false,
 "decided_by": null, "comment": null, "message": "Still waiting for a human."}
```

a human approved (via e-mail link or console):

```json
{"id": "79d647c1-…", "status": "approved", "approved": true,
 "decided_by": "<approver>", "decided_at": "2026-10-20T…", "comment": "owner mcp e2e approve",
 "message": "Approved by a human — proceed."}
```

a human rejected:

```json
{"status": "rejected", "approved": false, "message": "Rejected by a human — do not proceed."}
```

TTL elapsed, nobody decided:

```json
{"status": "expired", "approved": false,
 "message": "Not approved — the request expired before anyone decided."}
```

request_human_approval with wait_sec=8 and nobody answering:

```json
{"id": "ed2e963e-…", "status": "timeout", "approved": false, "decided_by": null,
 "message": "Not approved — nobody answered in 8s. The request is still open; check later with get_approval."}
```

Error shapes you will actually see:

get_approval on a foreign or unknown id — existence is never confirmed to a foreign key:

```text
Raposa API 404 on GET /v1/approvals/<id>: {"detail":"Approval not found"}
```

a decided approval does not flip: the second decision is refused by the API:

```text
Raposa API 409 on POST /v1/approvals/<id>/decision
```

## 7 · Who holds which power

| Role | Capability | Scope |
|---|---|---|
| **client** (the MCP key) | create, read, poll, receive webhooks for its own approvals | exactly its own approvals; foreign ids are 404 |
| **operator** (human decision path) | decide, list, verify the audit chain, export the audit | scoped to one customer or house-wide, by key configuration |
| **owner** | internal plan: unlimited monthly approvals, key management for its own account | unlimited quota, **not** unlimited privileges: the same rate limits, isolation and audit apply |

Nothing here makes an MCP client key an administrative credential. The administrative
surface (operator console) is a separate, credentialed place — not reachable with an MCP key.

## 8 · MCP Rush hosted listing

The same server is published on MCP Rush hosted infrastructure:
[darius-ceponas/raposa-aval-human-approval-mcp](https://mcprush.com/darius-ceponas/raposa-aval-human-approval-mcp)
— release 0.1.1, three tools, scanned and verified (trust score 96/100, grade A).
The gateway is live and refuses calls that carry no buyer token.

**Honest status:** the hosted release answers, but an end-to-end gateway call with real
buyer credentials has not been verified yet — the marketplace’s Access page (where a buyer
mints the required gateway key) was unreachable at the time of writing, and the publisher
has reported it to MCP Rush support. Until that lands, the direct `uvx` install in § 4 is
the supported way; this README makes no gateway end-to-end claim.

## 9 · Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RAPOSA_API_KEY is not set. Get a free sandbox key at …` | the variable did not reach the MCP process | export it in the shell that starts the client; check `claude mcp add` used the `${VAR}` placeholder, not an empty value |
| `HTTP 401 Invalid API key` on a direct API call | key revoked or mistyped | re-read the value from your vault; rotate from the account page |
| `404 Approval not found` on the right id | another key’s approval, or the id is mis-typed | approvals are tenant-scoped; use the key that created it |
| `429 … Rate limit exceeded (60/min for your plan)` | per-key per-minute rate limit (abuse guard, stays on every plan) | honour `Retry-After`; batch agent work |
| `409` on a second decision | the approval already reached a terminal state | terminal decisions are final and immutable |
| `timeout` with nobody awake | `wait_sec` elapsed at 5-second polling | the request stays open until TTL; ask the human, then `get_approval` |
| client hangs ~1 min on first call | cold start of a hosted/gateway server or package cache | retry; the second call is fast |
| claim link says `410 gone` | the one-time link was already opened or expired (24 h) | the key was already shown once; register again to receive a new link |

## 10 · Development

This repository — the MCP package itself:

```bash
pip install -e ".[test]" && pytest -q
```

11 contract tests run against a mocked transport: tools are listed with their schemas;
approve / reject / timeout / expiry all read back fail-closed; create returns an id without
waiting; API errors are reported, not swallowed; an unknown risk never reaches the API; a
missing key is a clear error while the tool listing still works.

The **backend API** (quotas, key rotation, one-time claim links, tenant isolation, panel
scopes, rate limiting, webhooks, Stripe, Slack/Telegram channels, audit chain) is a separate
repository with its own suite; these pytest runs do not exercise it.

* Source and issues: https://github.com/agentlabbusiness/raposa-mcp
* Documentation: https://raposa.group/docs/
* Legal: MIT License — © DC ESCRYPT SL (see [LICENSE](LICENSE))
* Contact: contact@raposa.group

Raposa Aval is a DC ESCRYPT product.