# raposa-mcp

[![Raposa Aval — human approval MCP on mcprush](https://mcprush.com/badge/darius-ceponas-raposa-aval-human-approval-mcp/score.svg)](https://mcprush.com/darius-ceponas/raposa-aval-human-approval-mcp)

An MCP server that gives your agent one honest tool: **ask a human**.

Raposa Aval is a DC ESCRYPT product — https://raposa.group.

```
request_human_approval(action, context, risk) -> { approved: true|false, decided_by, ... }
```

`approved` is `true` only when a named person pressed Approve. A timeout, an expiry or a rejection all
return `approved: false` — silence is not consent. Every decision is sealed in Raposa's hash-chained
audit log, exportable for an auditor. EU-hosted, DPA available.

<!-- mcp-name: group.raposa/raposa-mcp -->

## Getting a key

Register a free sandbox (100 approvals a month) at https://raposa.group/start/. You receive a
**one-time claim link by email, valid for 24 hours**: opening it reveals your API key once, and
the link cannot be used again. The key only travels through that link — never in chat tickets.

## Install

### Direct: uvx (works today)

```json
{
  "mcpServers": {
    "raposa": {
      "command": "uvx",
      "args": ["raposa-mcp"],
      "env": { "RAPOSA_API_KEY": "<your key>" }
    }
  }
}
```

Claude Code, without pasting the key on the command line:

```bash
export RAPOSA_API_KEY   # keep it in your environment (a secret manager is fine), never in history
claude mcp add raposa -e RAPOSA_API_KEY='${RAPOSA_API_KEY}' -- uvx raposa-mcp
claude mcp get raposa   # shows the ${...} reference, not the secret
```

Claude Code stores the `${RAPOSA_API_KEY}` reference and expands it from your environment when the
server starts — the key itself never lands in the config file or the shell history.

### MCP Rush gateway (published; buyer install pending marketplace fix)

The same server is hosted on MCP Rush as
[darius-ceponas/raposa-aval-human-approval-mcp](https://mcprush.com/darius-ceponas/raposa-aval-human-approval-mcp),
release 0.1.1, scanned and verified (trust score 96/100). The gateway serves it and refuses calls
without a buyer token. Buyer installs are blocked on the marketplace side until its Access page
returns — reported to MCP Rush support as case `p_4785` on 2026-10-20 — so until then the direct
`uvx` install above is the supported way; no gateway end-to-end claim is made here.

## Tools

| Tool | What it does |
|---|---|
| `request_human_approval(action, context, risk, requested_by?, wait_sec=600, expires_in_sec?)` | creates the request and waits for a human; returns `approved` |
| `create_approval(action, context, risk, requested_by?, expires_in_sec?, webhook_url?)` | returns the id at once; decision arrives on the HMAC-signed webhook or via `get_approval` |
| `get_approval(approval_id)` | reads one approval |

`risk` is `low | medium | high`. The API key is read from `RAPOSA_API_KEY` only and never appears in tool
inputs or outputs. Base URL override: `RAPOSA_API_BASE` (default `https://dcescrypt.com/api`).

## Who approves

The people on your team who hold the approve button get a scoped console login and, if you give us their
email, every request also reaches them as a mail with signed Approve / Reject links. Their name is recorded on
the decision. Docs: https://raposa.group/docs/#approvers

## Develop

```bash
pip install -e ".[test]" && pytest -q
```

Raposa Aval — a DC ESCRYPT product · https://raposa.group · contact@raposa.group
Legal: MIT license · © DC ESCRYPT SL
