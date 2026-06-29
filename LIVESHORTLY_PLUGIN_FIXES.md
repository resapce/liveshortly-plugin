# LiveShortly Claude Code plugin — migration & production fixes

A handoff for anyone running the same plugin who needs to point it at a hosted
backend and make it actually run. Two classes of change:

1. **API migration** — the backend moved `/api/live/*` → `/api/sessions/*`. The old
   routes now **404**, so the plugin breaks until updated.
2. **Runtime fixes** — bugs that stop the plugin from running at all (Python 3.9
   crash, missing share-URL, localhost-only fork links).

Tested end-to-end against a hosted backend (`https://liveshortly.com`).

---

## 1. API endpoint migration (`/api/live/*` → `/api/sessions/*`)

| Action | OLD route | NEW route | Notes |
|--------|-----------|-----------|-------|
| Create session | `POST /api/live/start` | `POST /api/sessions` | body `{title, model, framework}`; returns `{id}` (was `{session_id}`); success is **2xx** not strictly `201` |
| Stop session | `POST /api/live/:id/stop` | `POST /api/sessions/:id/stop` | returns the **session object** (no `url` field) — see fix #2 |
| Emit event | `POST /api/live/:id/emit` | `POST /api/sessions/:id/events` | body now also needs `actor` |
| Poll comments | `GET /api/live/:id/comments/pending` | `GET /api/sessions/:id/comments/pending` | drains (pops) the queue on read |

Web/share link path also changed: `/live/:id` → `/session/:id`.

Files touched: `hooks/lib/common.py`, `channel/channel.ts`, `hooks/events/live_session_start.py`.

---

## 2. Runtime fixes (without these the plugin does not run)

### a) MCP server crashes on Python 3.9  ← most important
`server/mcp_server.py` used PEP 604 type hints (`dict | None`) which require
Python **3.10+**. The plugin launches it with bare `python3`, which is **3.9** on
stock macOS → `TypeError: unsupported operand type(s) for |` **at import**, so the
MCP server never starts.

**Fix:** add as the first statement after the module docstring:
```python
from __future__ import annotations  # PEP 604 (dict | None) on Python 3.9
```
(Defers annotation evaluation to strings; works on 3.9. Alternative: rewrite hints
as `Optional[dict]`.)

### b) `live_stop()` returned `None` (no archive link)
The new `/stop` returns the session object with **no `url` field**, so
`data.get("url")` was always `None`.

**Fix:** fall back to building the link from the session id:
```python
return data.get("url") or f"{web_url()}/session/{data.get('id', live_id)}"
```

### c) Fork links hard-coded to localhost
`handle_fork_trace` in `mcp_server.py` only read the legacy `*_FRONTEND_URL` vars.

**Fix:** read `LIVESHORTLY_WEB_URL` first (matches the hooks' `web_url()` precedence)
and `.rstrip("/")`.

---

## 3. Configuration — point the plugin at the hosted backend

The code is **env-var driven** (with localhost fallbacks), so production is just
config — no code copy needed. Set these so **hooks + MCP servers + channel** all
hit prod. Easiest single place is Claude Code `~/.claude/settings.json`:

```json
{
  "env": {
    "LIVESHORTLY_API_URL": "https://liveshortly.com",
    "LIVESHORTLY_WEB_URL": "https://liveshortly.com"
  }
}
```

Env-var precedence in the code:
- API base: `LIVESHORTLY_API_URL` → `LEMMAY_API_URL` → `http://localhost:8000`
- Web base: `LIVESHORTLY_WEB_URL` → `LIVESHORTLY_FRONTEND_URL` → `LEMMAY_FRONTEND_URL` → `http://localhost:3000`

> `settings.json env` applies at Claude Code **startup** — restart for it to take effect.
> It propagates to plugin hooks *and* MCP server subprocesses.

---

## 4. Operational gotchas

- **Restart required.** Already-running hooks/MCP keep their old env until restart.
- **Channel needs deps.** Run `bun install` in `channel/` (the `zod` dep must be
  present) or the bun channel won't boot.
- **Port 8788 conflict.** `channel.ts` runs `lsof -ti :8788 | xargs kill -9` on
  startup — it will kill whatever else holds that port. Change `CHANNEL_PORT` if
  needed.
- **Python:** hooks run via `hooks/lm-python.sh` (any `python3`); the MCP server is
  launched with bare `python3` from `plugin.json`. Both are 3.9 on macOS — keep the
  `from __future__ import annotations` fix.

---

## 5. Known backend gap (not a plugin bug)

These trace-browse routes **404** on the hosted backend, so the MCP tools that use
them error until the routes are deployed server-side:

| MCP tool | Route (404) |
|----------|-------------|
| `search_traces` | `GET /api/search` |
| `get_trace` | `GET /api/traces/:id` |
| `get_feed` | `GET /api/feed` |
| `fork_trace` | `POST /api/fork/:id` |

The **core live-session flow** (create / emit events / poll comments / stop) works.

---

## 6. Smoke test (verify against any backend)

```bash
cd <plugin-dir>
export LIVESHORTLY_API_URL=https://liveshortly.com
export LIVESHORTLY_WEB_URL=https://liveshortly.com

# hooks pipeline
python3 - <<'PY'
import sys; sys.path.insert(0,"hooks/lib")
import common
lid = common.live_start(title="smoke")
print("start:", lid)
common.emit_event(lid, "prompt", {"content":"hi","ts":common.now()})
print("comments:", common.fetch_viewer_comments(lid))
print("stop:", common.live_stop(lid))
PY

# MCP server boots + lists tools
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 server/mcp_server.py

# channel boots (alt port so it doesn't kill 8788)
CHANNEL_PORT=8799 bun run channel/channel.ts &   # expect "comment poller started" + "listening"
```

---

## 7. Full diff (apply to a clean copy of the plugin)

```diff
diff --git a/.claude-plugin/plugin.json b/.claude-plugin/plugin.json
@@
-  "version": "2.3.0",
+  "version": "2.4.0",

# (also: delete the stale, pre-rebrand ".claude-plugin/plugin copy.json")

diff --git a/channel/channel.ts b/channel/channel.ts
@@ async function pollComments() {
-    const resp = await fetch(`${API_URL}/api/live/${liveId}/comments/pending`)
+    const resp = await fetch(`${API_URL}/api/sessions/${liveId}/comments/pending`)

diff --git a/hooks/events/live_session_start.py b/hooks/events/live_session_start.py
@@ def main():
     cwd = data.get("cwd", "")
+    source = data.get("source") or "startup"
+    base = os.path.basename(os.path.normpath(cwd)) if cwd else "session"
+    if not base or base in (".", "/"):
+        base = "session"
+    title = f"{base} ({source})"
@@
-        live_id = common.live_start(timeout=25)
+        live_id = common.live_start(title=title, timeout=25)
@@
-        frontend_url = (
-            os.environ.get("LIVESHORTLY_FRONTEND_URL")
-            or os.environ.get("LEMMAY_FRONTEND_URL")
-            or "http://localhost:3000"
-        )
-        live_url = f"{frontend_url}/live/{live_id}"
+        live_url = f"{common.web_url()}/session/{live_id}"

diff --git a/hooks/lib/common.py b/hooks/lib/common.py
@@ def _api_url() -> str:
     return url.rstrip("/")
+
+def web_url() -> str:
+    """Base URL of the LiveShortly web app (for shareable links)."""
+    url = (
+        os.environ.get("LIVESHORTLY_WEB_URL")
+        or os.environ.get("LIVESHORTLY_FRONTEND_URL")
+        or os.environ.get("LEMMAY_FRONTEND_URL")
+        or "http://localhost:3000"
+    )
+    return url.rstrip("/")
@@ live session helpers
-def live_start(timeout: int = 25):
-    """Start a live session. Returns session_id or None."""
-    data, status = api_post("/api/live/start", timeout=timeout)
-    if status == 201 and data:
-        return data.get("session_id")
+def live_start(title: str = "session", model: str = "claude",
+               framework: str = "claude-code", timeout: int = 25):
+    """Create a live session. Returns the session id or None."""
+    data, status = api_post("/api/sessions", {
+        "title": title, "model": model, "framework": framework,
+    }, timeout=timeout)
+    if data and 200 <= status < 300:
+        return data.get("id")
     return None

-def live_stop(live_id: str, timeout: int = 25):
-    data, status = api_post(f"/api/live/{live_id}/stop", timeout=timeout)
-    if status == 200 and data:
-        return data.get("url")
+def live_stop(live_id: str, timeout: int = 25):
+    data, status = api_post(f"/api/sessions/{live_id}/stop", timeout=timeout)
+    if data and 200 <= status < 300:
+        return data.get("url") or f"{web_url()}/session/{data.get('id', live_id)}"
     return None

-def emit_event(live_id, event_type, payload_dict, timeout: int = 10) -> None:
-    api_post(f"/api/live/{live_id}/emit", {
-        "event_type": event_type, "payload": payload_dict,
+def emit_event(live_id, event_type, payload_dict, actor: str = "agent", timeout: int = 10) -> None:
+    api_post(f"/api/sessions/{live_id}/events", {
+        "event_type": event_type, "payload": payload_dict, "actor": actor,
     }, timeout=timeout)

-def fetch_viewer_comments(live_id, timeout: int = 8) -> list:
-    data, status = api_get(f"/api/live/{live_id}/comments/pending", timeout=timeout)
-    if status == 200 and data:
+def fetch_viewer_comments(live_id, timeout: int = 8) -> list:
+    data, status = api_get(f"/api/sessions/{live_id}/comments/pending", timeout=timeout)
+    if data and 200 <= status < 300:
         return data.get("comments", [])
     return []

diff --git a/server/mcp_server.py b/server/mcp_server.py
@@ (top, after docstring)
+from __future__ import annotations  # PEP 604 (dict | None) on Python 3.9
@@ def handle_fork_trace(args: dict) -> str:
     frontend = (
-        os.environ.get("LIVESHORTLY_FRONTEND_URL")
+        os.environ.get("LIVESHORTLY_WEB_URL")
+        or os.environ.get("LIVESHORTLY_FRONTEND_URL")
         or os.environ.get("LEMMAY_FRONTEND_URL")
         or "http://localhost:3000"
-    )
+    ).rstrip("/")
```

---

PR with all of the above: `resapce/plugin#1` (branch `migrate-api-sessions`).
