"""Shared utilities for all liveshortly hook scripts."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


# ── Config ────────────────────────────────────────────────────────────────────

def _api_url() -> str:
    url = (
        os.environ.get("LIVESHORTLY_API_URL")
        or os.environ.get("LEMMAY_API_URL")
        or "http://localhost:8000"
    )
    return url.rstrip("/")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method: str, path: str, body=None, timeout: int = 10):
    """Make an HTTP request. Returns (data_dict_or_None, status_code). Never raises."""
    try:
        url = _api_url() + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, 0


def api_get(path: str, timeout: int = 10):
    return _request("GET", path, timeout=timeout)


def api_post(path: str, body=None, timeout: int = 10):
    return _request("POST", path, body=body, timeout=timeout)


# ── Live session helpers ──────────────────────────────────────────────────────

def live_start(timeout: int = 25):
    """Start a live session. Returns session_id or None."""
    data, status = api_post("/api/live/start", timeout=timeout)
    if status == 201 and data:
        return data.get("session_id")
    return None


def live_stop(live_id: str, timeout: int = 25):
    """Stop a live session and archive it. Returns the trace URL or None."""
    data, status = api_post(f"/api/live/{live_id}/stop", timeout=timeout)
    if status == 200 and data:
        return data.get("url")
    return None


def emit_event(live_id: str, event_type: str, payload_dict: dict, timeout: int = 10) -> None:
    """Emit an event into the live session feed."""
    api_post(f"/api/live/{live_id}/emit", {
        "event_type": event_type,
        "payload": payload_dict,
    }, timeout=timeout)


def fetch_viewer_comments(live_id: str, timeout: int = 8) -> list:
    """Pop all pending viewer comments for this session."""
    data, status = api_get(f"/api/live/{live_id}/comments/pending", timeout=timeout)
    if status == 200 and data:
        return data.get("comments", [])
    return []


# ── General utilities ─────────────────────────────────────────────────────────

def truncate(text, max_len: int = 2000) -> str:
    if not text:
        return ""
    s = str(text)
    return s[:max_len] + "…" if len(s) > max_len else s


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def notify(message: str) -> None:
    """Write a visible notification to stderr (shown in Claude Code status bar)."""
    print(f"[liveshortly] {message}", file=sys.stderr)


def read_stdin() -> dict:
    """Read and parse JSON from stdin. Returns empty dict on any error."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def done(output=None) -> None:
    """Emit JSON response to stdout and exit 0. Must always be called."""
    print(json.dumps(output or {}))
    sys.exit(0)
