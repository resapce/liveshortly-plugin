"""
Per-session state management for the liveshortly plugin.
State stored at ~/.claude/liveshortly/state_<session_id>.json with fcntl locking.
"""
try:
    import fcntl
except ImportError:
    fcntl = None

import json
import os
import re

STATE_DIR = os.path.expanduser("~/.claude/liveshortly")
CURRENT_FILE = os.path.join(STATE_DIR, "current.json")


def _safe_key(session_id):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id))[:128]


def _state_path(session_id):
    return os.path.join(STATE_DIR, f"state_{_safe_key(session_id)}.json")


def _lock_path(session_id):
    return os.path.join(STATE_DIR, f"state_{_safe_key(session_id)}.lock")


def set_current_live_session(live_id: str) -> None:
    """Write the active live session ID to the well-known current.json file."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CURRENT_FILE, "w") as f:
        json.dump({"live_session_id": live_id}, f)


def clear_current_live_session() -> None:
    """Remove current.json when the live session ends."""
    try:
        os.remove(CURRENT_FILE)
    except OSError:
        pass


def load(session_id):
    try:
        with open(_state_path(session_id)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save(session_id, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_state_path(session_id), "w") as f:
        json.dump(data, f)


def with_locked_state(session_id, callback):
    """Run callback(state) with exclusive file lock; saves state on return."""
    os.makedirs(STATE_DIR, exist_ok=True)
    lock_path = _lock_path(session_id)

    if fcntl is None:
        state = load(session_id)
        result = callback(state)
        save(session_id, state)
        return result

    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        state = load(session_id)
        result = callback(state)
        save(session_id, state)
        return result
    except (OSError, IOError):
        return None
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except (OSError, IOError):
                pass
