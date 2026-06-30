"""Shared utilities for all liveshortly hook scripts."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth  # noqa: E402  (shared credential layer — bearer auth + refresh)


# ── Config ────────────────────────────────────────────────────────────────────

def _api_url() -> str:
    return auth.api_url()


def web_url() -> str:
    """Base URL of the LiveShortly web app (for shareable links)."""
    return auth.web_url()


# ── HTTP helpers ──────────────────────────────────────────────────────────────

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _send(method: str, path: str, body=None, timeout: int = 10):
    """Single HTTP attempt with bearer auth. Returns (data|None, status)."""
    try:
        url = _api_url() + path
        data = json.dumps(body).encode() if body is not None else None
        # Bearer token identifies the signed-in user; {} if not logged in.
        headers = dict(auth.auth_headers())
        headers["User-Agent"] = _UA
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, 0


def _request(method: str, path: str, body=None, timeout: int = 10):
    """Make an HTTP request. Returns (data_dict_or_None, status_code). Never raises.

    On a 401 the access token is refreshed once and the request is retried.
    """
    data, status = _send(method, path, body=body, timeout=timeout)
    if status == 401:
        try:
            if auth.refresh():
                data, status = _send(method, path, body=body, timeout=timeout)
        except Exception:
            pass
    return data, status


def api_get(path: str, timeout: int = 10):
    return _request("GET", path, timeout=timeout)


def api_post(path: str, body=None, timeout: int = 10):
    return _request("POST", path, body=body, timeout=timeout)


# ── Live session helpers ──────────────────────────────────────────────────────

def live_start(title: str = "session", model: str = None,
               framework: str = "claude-code", timeout: int = 25):
    """Create a live session. Returns the session id or None.

    `model` is omitted when unknown (a fresh session has no assistant turn yet);
    the true model is reported later via report_model() once the transcript
    reveals it.
    """
    body = {"title": title, "framework": framework}
    if model:
        body["model"] = model
    data, status = api_post("/api/sessions", body, timeout=timeout)
    if data and 200 <= status < 300:
        return data.get("id")
    return None


def report_model(live_id: str, model: str, timeout: int = 8) -> bool:
    """Set the session's model label (owner-only PATCH). Returns True on success."""
    if not (live_id and model):
        return False
    _, status = _request("PATCH", f"/api/sessions/{live_id}", {"model": model},
                         timeout=timeout)
    return 200 <= status < 300


def detect_model(transcript_path: str):
    """Best-effort: read the model id from the session transcript.

    Claude Code writes a JSONL transcript; each assistant turn carries
    `message.model` (e.g. "claude-opus-4-8"). Scans from the end for the most
    recent assistant model. Returns the model id or None.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    try:
        with open(transcript_path, "r") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        msg = obj.get("message")
        if isinstance(msg, dict):
            model = msg.get("model")
            if model and model != "<synthetic>":
                return model
    return None


def live_stop(live_id: str, timeout: int = 25):
    """Stop a live session and archive it. Returns the trace URL or None."""
    data, status = api_post(f"/api/sessions/{live_id}/stop", timeout=timeout)
    if data and 200 <= status < 300:
        # Prefer a server-provided url; otherwise build the shareable link
        # from the session id (the /stop response returns the session object).
        return data.get("url") or f"{web_url()}/session/{data.get('id', live_id)}"
    return None


def emit_event(live_id: str, event_type: str, payload_dict: dict,
               actor: str = "agent", timeout: int = 10) -> None:
    """Emit an event into the live session feed."""
    api_post(f"/api/sessions/{live_id}/events", {
        "event_type": event_type,
        "payload": payload_dict,
        "actor": actor,
    }, timeout=timeout)


def fetch_viewer_comments(live_id: str, timeout: int = 8) -> list:
    """Pop all pending viewer comments for this session."""
    data, status = api_get(f"/api/sessions/{live_id}/comments/pending", timeout=timeout)
    if data and 200 <= status < 300:
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
