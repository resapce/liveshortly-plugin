#!/usr/bin/env python3
"""Shared credential layer for the liveshortly plugin.

Implements the device-flow OAuth login and a shared local credential store at
~/.liveshortly/credentials.json that every client (hooks, MCP server, channel)
reads to send `Authorization: Bearer <access_token>` and auto-refresh.

Stdlib only (urllib, webbrowser, json, hashlib). See AUTH.md for the contract.

Standalone usage:
    python3 auth.py login     # device-flow browser login, stores creds
    python3 auth.py logout     # delete creds
    python3 auth.py whoami     # print the signed-in identity
"""
from __future__ import annotations  # dict | None on Python 3.9

import json
import os
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone


# ── Config ────────────────────────────────────────────────────────────────────

def cred_path() -> str:
    override = os.environ.get("LIVESHORTLY_CRED_PATH", "").strip()
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.liveshortly/credentials.json")


CRED_PATH = cred_path()


def host_path() -> str:
    return os.path.expanduser("~/.liveshortly/host.json")


def load_host() -> dict:
    """Load ~/.liveshortly/host.json. Returns {} if missing."""
    try:
        with open(host_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def api_url() -> str:
    host = load_host()
    return (
        host.get("api_url")
        or os.environ.get("LIVESHORTLY_API_URL")
        or "http://localhost:8000"
    ).rstrip("/")


def web_url() -> str:
    host = load_host()
    return (
        host.get("web_url")
        or os.environ.get("LIVESHORTLY_WEB_URL")
        or os.environ.get("LIVESHORTLY_FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")


# ── Credential store ──────────────────────────────────────────────────────────

def load_creds() -> dict | None:
    """Load credentials.json. Returns the dict or None if missing/unreadable."""
    try:
        with open(cred_path(), "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_creds(d: dict) -> None:
    """Write credentials.json with mode 0600, creating the parent dir."""
    path = cred_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _delete_creds() -> None:
    try:
        os.remove(cred_path())
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ── time helpers ──────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expiry_iso(expires_in: int) -> str:
    """RFC3339 timestamp `expires_in` seconds from now."""
    return (_now() + timedelta(seconds=int(expires_in))).isoformat()


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ── HTTP ──────────────────────────────────────────────────────────────────────

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _http(method: str, path: str, body: dict | None = None, timeout: int = 15):
    """Returns (data_dict_or_None, status_code, headers_dict). Never raises."""
    url = api_url() + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": _UA}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            parsed = json.loads(raw) if raw else {}
            return parsed, resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read())
        except Exception:
            parsed = None
        return parsed, e.code, dict(e.headers or {})
    except Exception:
        return None, 0, {}


def _http_auth(method: str, path: str, body: dict | None = None, timeout: int = 15):
    """Like _http but adds the bearer token (used by whoami)."""
    url = api_url() + path
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(auth_headers())
    headers["User-Agent"] = _UA
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, 0


# ── Tokens ────────────────────────────────────────────────────────────────────

def access_token() -> str | None:
    """Return a valid access token, refreshing if it's within 60s of expiry."""
    creds = load_creds()
    if not creds:
        return None
    exp = _parse_iso(creds.get("expires_at", ""))
    if exp is not None and _now() >= (exp - timedelta(seconds=60)):
        return refresh()
    return creds.get("access_token")


def refresh() -> str | None:
    """Mint a fresh access token from the stored refresh token.

    On success updates access_token/refresh_token/expires_at and saves.
    On failure (401 / bad refresh) deletes the creds file and returns None.
    """
    creds = load_creds()
    if not creds or not creds.get("refresh_token"):
        return None
    data, status, _ = _http("POST", "/auth/token", {
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"],
    })
    if data and 200 <= status < 300 and data.get("access_token"):
        creds["access_token"] = data["access_token"]
        # refresh tokens may be rotated by the server
        if data.get("refresh_token"):
            creds["refresh_token"] = data["refresh_token"]
        if data.get("expires_in"):
            creds["expires_at"] = _expiry_iso(data["expires_in"])
        save_creds(creds)
        return creds["access_token"]
    if status == 401:
        _delete_creds()
    return None


def auth_headers() -> dict:
    """Bearer header if a token exists, else {} so calls degrade gracefully."""
    tok = access_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ── Device flow ───────────────────────────────────────────────────────────────

def login(open_browser: bool = True, timeout: int = 180) -> dict | None:
    """Run the device-flow browser login and store the resulting tokens.

    Returns the user dict ({email, name}) on success, or None on failure.
    """
    start, status, _ = _http("POST", "/auth/device/start", {})
    if not start or not (200 <= status < 300):
        print("[liveshortly] Could not start device login (is the API running?)",
              file=sys.stderr)
        return None

    device_code = start.get("device_code")
    verify_url = start.get("verification_uri_complete") or start.get("verification_uri")
    if verify_url:
        verify_url = verify_url.replace("https://server.liveshortly.com", "https://liveshortly.com")
        verify_url = verify_url.replace("http://server.liveshortly.com", "https://liveshortly.com")
    interval = int(start.get("interval", 5)) or 5
    expires_in = int(start.get("expires_in", 600)) or 600

    if not device_code or not verify_url:
        print("[liveshortly] Malformed device/start response.", file=sys.stderr)
        return None

    print(f"Open this URL to sign in: {verify_url}", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(verify_url)
        except Exception:
            pass

    deadline = time.time() + min(timeout, expires_in)
    while time.time() < deadline:
        time.sleep(interval)
        data, st, _ = _http("POST", "/auth/device/poll", {"device_code": device_code})
        if data is None:
            continue
        if st == 200 and data.get("access_token"):
            user = data.get("user") or {}
            save_creds({
                "api_url": api_url(),
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": _expiry_iso(data.get("expires_in", 3600)),
                "user": user,
            })
            email = user.get("email") or "user"
            print(f"✓ Logged in as {email}", file=sys.stderr)
            return user
        # status == "pending" (or any non-token 200) → keep polling
    print("[liveshortly] Login timed out before approval.", file=sys.stderr)
    return None


def setup(url: str = "https://liveshortly.com") -> None:
    """Write ~/.liveshortly/host.json with the given base URL.

    Both api_url and web_url are set to the same value; edit the file
    manually if you need them to differ (e.g. dev with separate ports).
    """
    url = url.rstrip("/")
    path = host_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"api_url": url, "web_url": url}, f, indent=2)
    print(f"Host config written to {path}", file=sys.stderr)
    print(f"  api_url: {url}", file=sys.stderr)
    print(f"  web_url: {url}", file=sys.stderr)


def logout() -> None:
    """Delete the local credentials file."""
    _delete_creds()


def whoami() -> dict | None:
    """Return the current identity from GET /api/me, or None if not signed in."""
    if not access_token():
        return None
    data, status = _http_auth("GET", "/api/me")
    if data and 200 <= status < 300 and data.get("authenticated", True):
        return data
    return None


# ── Standalone entrypoint ─────────────────────────────────────────────────────

def _main(argv: list) -> int:
    cmd = (argv[0] if argv else "").lower()
    if cmd == "setup":
        url = argv[1] if len(argv) > 1 else "https://liveshortly.com"
        setup(url)
        return 0
    if cmd == "login":
        user = login()
        return 0 if user else 1
    if cmd == "logout":
        logout()
        print("Logged out.", file=sys.stderr)
        return 0
    if cmd == "whoami":
        me = whoami()
        if me:
            email = me.get("email") or me.get("id") or "?"
            name = me.get("name")
            print(f"{email}" + (f" ({name})" if name else ""))
        else:
            print("not signed in")
        return 0
    print("usage: python3 auth.py setup [url] | login | logout | whoami", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
