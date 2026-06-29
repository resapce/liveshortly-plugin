# liveshortly — Claude Code Plugin

A Claude Code plugin that live-streams your coding sessions to viewers in real time. Every prompt, tool call, and file write is emitted to the liveshortly API as a session event. Viewers can post comments that get injected back into Claude's context as channel notifications.

---

## How it works

```
Claude Code session
      │
      ├── SessionStart hook  →  POST /api/live/start  →  live_session_id
      │                                                        │
      │         ~/.claude/liveshortly/current.json ←──────────┘
      │
      ├── UserPromptSubmit hook  →  fetch pending viewer comments
      │                           →  inject as additionalContext
      │
      ├── PreToolUse hook   →  emit tool_call event
      ├── PostToolUse hook  →  emit file_write / bash_result event
      ├── Stop hook         →  emit response event (Claude's reply)
      │
      └── SessionEnd hook   →  POST /api/live/:id/stop  →  archived trace URL


channel MCP server (bun/Node.js)
      │
      ├── polls /api/live/:id/comments/pending every 3 s
      └── pushes new comments as notifications/claude/channel messages


liveshortly MCP server (Python)
      ├── search_traces   — search recorded sessions
      ├── get_trace       — read full conversation + tool calls
      ├── get_feed        — browse trending / latest / forked sessions
      └── fork_trace      — fork a session to create your own copy
```

---

## Directory structure

```
plugin/
├── .claude-plugin/
│   ├── plugin.json          # plugin manifest (name, version, mcpServers)
│   └── marketplace.json     # local marketplace entry for development
│
├── hooks/
│   ├── hooks.json           # event → script mappings
│   ├── lm-python.sh         # thin wrapper that runs hook scripts with correct PYTHONPATH
│   ├── lib/
│   │   ├── common.py        # shared HTTP helpers + live session helpers
│   │   └── state.py         # per-session JSON state with file locking
│   └── events/
│       ├── live_session_start.py   # SessionStart
│       ├── user_prompt_submit.py   # UserPromptSubmit
│       ├── pre_tool_use.py         # PreToolUse
│       ├── post_tool_use.py        # PostToolUse
│       ├── stop.py                 # Stop
│       └── session_end.py          # SessionEnd
│
├── server/
│   └── mcp_server.py        # MCP server — search_traces / get_trace / get_feed / fork_trace
│
├── channel/
│   └── channel.ts           # channel MCP server — HTTP bridge + comment poller
│
└── skills/
    └── install/SKILL.md     # /liveshortly:install skill
```

---

## Authentication

The plugin signs in with a **browser device-flow OAuth login** and stores tokens
in a shared credential file. Ownership of your sessions comes from the **signed-in
Google account**, not from a `user@hostname` handle. Every API call (hooks, MCP
server, channel poller) sends `Authorization: Bearer <access_token>` and the
access token is auto-refreshed when it nears expiry.

### Logging in

Either via the MCP `login` tool (the primary UX — ask Claude to run it), or from a
shell:

```bash
python3 <plugin>/hooks/lib/auth.py login    # opens the browser, polls, stores creds
python3 <plugin>/hooks/lib/auth.py whoami    # prints the signed-in identity
python3 <plugin>/hooks/lib/auth.py logout    # deletes the local credentials
```

`login` calls `POST /auth/device/start`, prints + opens the `verification_uri_complete`,
and polls `POST /auth/device/poll` until you approve in the browser.

MCP tools (same behaviour, runnable by the agent): **`login`**, **`logout`**, **`whoami`**.

### Credential store

File: `~/.liveshortly/credentials.json` (mode `0600`, override with `LIVESHORTLY_CRED_PATH`):

```json
{
  "api_url": "https://liveshortly.com",
  "access_token": "...",
  "refresh_token": "lsr_...",
  "expires_at": "2026-06-27T11:00:00+00:00",
  "user": { "email": "you@example.com", "name": "You" }
}
```

- **Auto-refresh:** when `now >= expires_at - 60s`, clients call `POST /auth/token`
  (`grant_type=refresh_token`), rewrite the file, and continue. A 401 also triggers
  one refresh-and-retry. If the refresh token is rejected (401), the file is deleted
  and the client falls back to unauthenticated.
- **Degrade gracefully:** with no creds (or a dead API) every client runs
  unauthenticated and never crashes. `SessionStart` simply notifies
  *"Not signed in — run the `login` tool"* and skips capture without blocking Claude.

> **Removed:** the old `X-LiveShortly-Handle` / `LIVESHORTLY_HANDLE` ownership model is
> gone. Identity now comes from your signed-in account.

## Configuration

All config is done through environment variables. No config files, no database.

### API / Frontend URLs

| Variable | Default | Purpose |
|---|---|---|
| `LIVESHORTLY_API_URL` | `http://localhost:8000` | liveshortly backend API (also used for the device-flow `/auth/*` endpoints) |
| `LEMMAY_API_URL` | _(fallback)_ | legacy alias for the same API |
| `LIVESHORTLY_CRED_PATH` | `~/.liveshortly/credentials.json` | override the shared credential file location |
| `LIVESHORTLY_FRONTEND_URL` | `http://localhost:3000` | frontend (used to build the viewer URL) |
| `LEMMAY_FRONTEND_URL` | _(fallback)_ | legacy alias for the same frontend |

Set these in your shell profile or in Claude Code's `~/.claude/settings.json`:

```json
{
  "env": {
    "LIVESHORTLY_API_URL": "https://api.liveshortly.io",
    "LIVESHORTLY_FRONTEND_URL": "https://liveshortly.io"
  }
}
```

### Channel server

| Variable | Default | Purpose |
|---|---|---|
| `CHANNEL_PORT` | `8788` | HTTP port the channel server listens on |
| `ALLOWED_SENDERS` | `dev` | Comma-separated list of allowed `X-Sender` header values |
| `COMMENT_POLL_MS` | `3000` | How often (ms) to poll for new viewer comments |

---

## State files

The plugin writes two kinds of state, both under `~/.claude/liveshortly/`:

### Per-session state — `<session_id>.json`

Written and read by the Python hook scripts. Stores:

```json
{
  "live_session_id": "uuid-of-the-active-live-session",
  "cwd": "/path/to/project",
  "started_at": "2026-06-27T10:00:00+00:00"
}
```

Access is protected by a `fcntl` file lock so concurrent hooks don't corrupt the file.

### Well-known current session — `current.json`

A fixed path that always points to the currently active live session:

```json
{ "live_session_id": "uuid-of-the-active-live-session" }
```

- **Written** by `live_session_start.py` after a session starts.
- **Cleared** (deleted) by `session_end.py` when the session ends.
- **Read** by the channel server's comment poller every `COMMENT_POLL_MS` milliseconds.

This indirection is necessary because the channel server (a separate process) doesn't know the Claude session ID — it only has access to this fixed path.

---

## Hook events

| Event | Script | What it does |
|---|---|---|
| `SessionStart` | `live_session_start.py` | Calls `POST /api/live/start`, writes `current.json`, injects viewer URL into Claude's system message |
| `UserPromptSubmit` | `user_prompt_submit.py` | Fetches pending viewer comments and injects them as `additionalContext` |
| `PreToolUse` | `pre_tool_use.py` | Emits a `tool_call` event to the live feed |
| `PostToolUse` | `post_tool_use.py` | Emits `file_write` or `bash_result` to the live feed |
| `Stop` | `stop.py` | Emits Claude's final response to the live feed |
| `SessionEnd` | `session_end.py` | Calls `POST /api/live/:id/stop`, deletes `current.json` |

---

## MCP servers

### `liveshortly-server` (Python — `server/mcp_server.py`)

Read-only tools for browsing the trace library. Talks to the API via `urllib` (no dependencies).

| Tool | API call | Description |
|---|---|---|
| `search_traces` | `GET /api/search?q=...` | Search sessions by keyword / tags / model |
| `get_trace` | `GET /api/traces/:id` | Full conversation + tool call history |
| `get_feed` | `GET /api/feed?type=...` | Trending / latest / most-forked sessions |
| `fork_trace` | `POST /api/fork/:id` | Fork a session to create your own copy |
| `login` | `POST /auth/device/start` + `/poll` | Browser device-flow sign-in; stores creds |
| `logout` | _(local)_ | Delete the local credentials |
| `whoami` | `GET /api/me` | Show the signed-in identity |

All trace-browse tools also send `Authorization: Bearer <access_token>` when signed in.

### `liveshortly-channel` (TypeScript — `channel/channel.ts`)

Two responsibilities:

1. **HTTP bridge** — accepts `POST /` to push a message into Claude as a channel notification, and `GET /events` for an SSE stream of Claude's replies.
2. **Comment poller** — reads `~/.claude/liveshortly/current.json` every `COMMENT_POLL_MS` ms, fetches `GET /api/live/:id/comments/pending`, and pushes each comment to Claude via `notifications/claude/channel`.

---

## Development setup

```bash
# 1. Install channel dependencies
cd channel && bun install

# 2. Point at your local API
export LIVESHORTLY_API_URL=http://localhost:8000
export LIVESHORTLY_FRONTEND_URL=http://localhost:3000

# 3. Load the plugin from this directory
claude --plugin-dir . --dangerously-load-development-channels plugin:liveshortly@liveshortly-local

# 4. Test the channel HTTP bridge (separate terminal)
curl -N localhost:8788/events                          # SSE stream
curl -d "hello from the bridge" -H "X-Sender: dev" localhost:8788
```

## Installing from the local marketplace

```bash
claude plugin marketplace update    # register the local marketplace
claude plugin update liveshortly    # install / upgrade the plugin
```

---

## API endpoints used

All calls go to `LIVESHORTLY_API_URL`. Requests carry `Authorization: Bearer <access_token>`
from `~/.liveshortly/credentials.json` (see [Authentication](#authentication)); the server
resolves the owning user from that token.

| Method | Path | Used by |
|---|---|---|
| `POST` | `/auth/device/start` | `auth.py` / `login` tool |
| `POST` | `/auth/device/poll` | `auth.py` / `login` tool |
| `POST` | `/auth/token` | token auto-refresh (all clients) |
| `GET` | `/api/me` | `whoami` tool |
| `POST` | `/api/sessions` | `live_session_start.py` |
| `POST` | `/api/sessions/:id/stop` | `session_end.py` |
| `POST` | `/api/sessions/:id/events` | `pre_tool_use.py`, `post_tool_use.py`, `stop.py` |
| `GET` | `/api/sessions/:id/comments/pending` | `user_prompt_submit.py`, `channel.ts` poller |
| `GET` | `/api/search` | `search_traces` tool |
| `GET` | `/api/traces/:id` | `get_trace` tool |
| `GET` | `/api/feed` | `get_feed` tool |
| `POST` | `/api/fork/:id` | `fork_trace` tool |
