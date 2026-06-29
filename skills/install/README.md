# LiveShortly Plugin — Install Guide

LiveShortly live-streams your Claude Code session to a web dashboard. Every prompt, tool call, and file edit is captured in real time. Share sessions like a Google Drive link and let viewers message back into your session.

**v3 uses browser-based Google sign-in — no tokens to copy.**

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Claude Code CLI | Required |
| `python3` | Hooks + MCP server (stdlib only, no pip install) |
| `bun` | Optional — only needed for the two-way viewer comment channel |
| Google account | Sign in once through your browser |

---

## Step 1 — Configure the backend URL

Add the following to `~/.claude/settings.json` so hooks and the MCP server point at the hosted backend:

```json
{
  "env": {
    "LIVESHORTLY_API_URL": "https://liveshortly.com",
    "LIVESHORTLY_WEB_URL": "https://liveshortly.com"
  }
}
```

> Omit these to stay on `http://localhost:8000` for local development.

---

## Step 2 — Install the plugin

### From GitHub (recommended — no clone needed)

```bash
claude plugin marketplace add https://github.com/resapce/plugin --scope user
claude plugin install liveshortly@liveshortly --scope user
claude plugin list   # should show: liveshortly  3.0.0  enabled
```

### From a local clone

```bash
git clone https://github.com/resapce/plugin liveshortly-plugin
claude plugin marketplace add "$PWD/liveshortly-plugin" --scope user
claude plugin install liveshortly@liveshortly --scope user
```

---

## Step 3 — Sign in (once per machine)

### Option A — from inside Claude Code

Ask Claude to run the `login` tool:

> "Please run the login tool"

It opens your browser → sign in with Google → click **Approve** → done.

### Option B — from a shell

```bash
python3 "$(claude plugin path liveshortly)/hooks/lib/auth.py" login
```

Credentials are saved to `~/.liveshortly/credentials.json` (mode `0600`) and auto-refresh — you never need to log in again unless you explicitly sign out.

Verify you're signed in:

```bash
python3 "$(claude plugin path liveshortly)/hooks/lib/auth.py" whoami
# or ask Claude: "run whoami"
```

---

## Step 4 — Use it

Just write code. At the start of each Claude Code session you'll see:

```
🔴 Recording live → https://liveshortly.com/session/<id>
```

**Dashboard** — go to [liveshortly.com](https://liveshortly.com). Your sessions appear under **MY SESSIONS**.

**Share a session** — click **SHARE** on any session row, add an email and choose VIEWER or COMMENTER. It appears under **SHARED WITH ME** for them.

**Viewer comments** — anyone with COMMENTER access can send messages while you're live. They're injected into your Claude context at the next prompt or tool use.

> If you're not signed in, capture is silently skipped and Claude keeps working normally. You'll see a "run the `login` tool" notice in the session header.

---

## Update

```bash
claude plugin update liveshortly@liveshortly
```

---

## Sign out / Uninstall

```bash
# Sign out (deletes local credentials only)
python3 "$(claude plugin path liveshortly)/hooks/lib/auth.py" logout

# Remove the plugin entirely
claude plugin uninstall liveshortly@liveshortly
```

---

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `LIVESHORTLY_API_URL` | `http://localhost:8000` | Backend API URL |
| `LIVESHORTLY_WEB_URL` | `http://localhost:3000` | Web app URL (used in shareable links) |
| `LIVESHORTLY_CRED_PATH` | `~/.liveshortly/credentials.json` | Override the credential file path |
| `CHANNEL_PORT` | `8788` | Port the viewer-comment channel server listens on |
| `COMMENT_POLL_MS` | `3000` | How often (ms) to poll for new viewer comments |

---

## Troubleshooting

**"Not signed in" at session start**
Run the `login` tool or `auth.py login` (Step 3).

**401 errors / capture stops mid-session**
The access token expired and the refresh token was rejected. Run `login` again.

**Sessions don't appear in the dashboard**
1. Check `LIVESHORTLY_API_URL` is set correctly.
2. Restart Claude Code — hooks load at session start, not mid-session.
3. Run `whoami` to confirm your identity is recognized.

**Channel comments aren't injecting**
Make sure `bun` is installed and `CHANNEL_PORT` isn't blocked by another process. Check `~/.claude/liveshortly/current.json` exists during an active session.
