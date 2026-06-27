---
name: install-liveshortly
description: Install, set up, sign in to, update, or uninstall the LiveShortly plugin (v3). Run this skill to get the plugin capturing your Claude Code sessions.
---

# LiveShortly plugin — setup (v3)

LiveShortly live-streams your Claude Code session to a web dashboard: it captures
your prompts, tool calls, and file edits; lets you **share** sessions Google-Drive
style; and lets viewers **message back** into your session. v3 uses **browser-based
sign-in** (no tokens to copy) — your sessions are owned by your Google account.

Default backend: **https://server.liveshortly.com**

---

## Prerequisites
- Claude Code CLI
- `python3` (hooks + MCP, stdlib only)
- `bun` (only for the two-way comment channel; optional)
- A Google account (you sign in through the browser)

---

## 1. Point the plugin at the backend

Add this to your `~/.claude/settings.json` (`env` block) so the plugin and its
hooks talk to the hosted backend:

```json
{
  "env": {
    "LIVESHORTLY_API_URL": "https://server.liveshortly.com",
    "LIVESHORTLY_WEB_URL": "https://server.liveshortly.com"
  }
}
```

(Leave these out to default to `http://localhost:8000` for local development.)

## 2. Install the plugin

Clone the repo, register it as a local marketplace, and install:

```bash
git clone git@github.com:resapce/plugin.git liveshortly-plugin
claude plugin marketplace add "$PWD/liveshortly-plugin" --scope user
claude plugin install liveshortly@liveshortly-local --scope user
claude plugin list      # verify "liveshortly  3.0.0  enabled"
```

> If the marketplace got a different name, re-run `marketplace add` and use the
> name it prints in the `install` command.

## 3. Sign in (one time)

Start Claude Code, then authenticate. Two ways:

- **From inside Claude Code** — ask it to run the **`login`** tool (the MCP exposes
  `login`, `logout`, `whoami`). It opens your browser → sign in with Google →
  **Approve** → return to the terminal.
- **From a shell**:
  ```bash
  python3 "$(claude plugin path liveshortly)/hooks/lib/auth.py" login
  ```

This stores a refreshing token at `~/.liveshortly/credentials.json` (mode 600).
Verify with the `whoami` tool or `… auth.py whoami`.

## 4. Use it

Just code. On the next session start you'll see:

```
🔴 Recording live → https://server.liveshortly.com/session/<id>
```

- Open the dashboard at **https://server.liveshortly.com** → your runs appear under
  **MY SESSIONS**.
- **Share** a session (owner): click **SHARE** on its row → add an email + role
  (VIEWER / COMMENTER). It shows up under **SHARED WITH ME** for them.
- **Viewers** watching a live session can send a message; it's injected into your
  Claude context on your next prompt or tool use.

If you're not signed in, capture is skipped and you'll see a "run the `login` tool"
notice — Claude keeps working normally.

---

## Update

```bash
git -C liveshortly-plugin pull
claude plugin marketplace update liveshortly-local
claude plugin update liveshortly@liveshortly-local
```

## Sign out / uninstall

```bash
python3 "$(claude plugin path liveshortly)/hooks/lib/auth.py" logout   # clear creds
claude plugin uninstall liveshortly@liveshortly-local
```

## Config reference
| Env var | Default | Purpose |
|---|---|---|
| `LIVESHORTLY_API_URL` | `http://localhost:8000` | backend API |
| `LIVESHORTLY_WEB_URL` | `http://localhost:3000` | web app (shareable links) |
| `LIVESHORTLY_CRED_PATH` | `~/.liveshortly/credentials.json` | token store |
| `CHANNEL_PORT` | `8788` | comment channel port |
| `COMMENT_POLL_MS` | `3000` | viewer-comment poll interval |

## Troubleshooting
- **"Not signed in"** → run the `login` tool (step 3).
- **401s / capture stops** → token expired and refresh failed; run `login` again.
- **Nothing appears in the dashboard** → check `LIVESHORTLY_API_URL`, then restart
  Claude Code (hooks load at session start), then `whoami` to confirm identity.
