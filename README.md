# raposa-mcp

An MCP server that gives your agent one honest tool: **ask a human**.

```
request_human_approval(action, context, risk) -> { approved: true|false, decided_by, ... }
```

`approved` is `true` only when a named person pressed Approve. A timeout, an expiry or a rejection all
return `approved: false` — silence is not consent. Every decision is sealed in Raposa's hash-chained
audit log, exportable for an auditor. EU-hosted, DPA available.

## Install

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

Claude Code: `claude mcp add raposa -e RAPOSA_API_KEY=<your key> -- uvx raposa-mcp`

Until the PyPI release lands, install straight from GitHub (identical code):

```bash
claude mcp add raposa -e RAPOSA_API_KEY=<your key> -- uvx --from git+https://github.com/agentlabbusiness/raposa-mcp raposa-mcp
```

Get a free sandbox key (100 approvals a month) at https://raposa.group/start/ — it arrives by email in a minute.

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

MIT · DC ESCRYPT SL · contact@raposa.group
