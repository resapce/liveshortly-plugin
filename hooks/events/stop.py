#!/usr/bin/env python3
"""Stop hook — records Claude's response and signals turn completion to viewers.

This is also where a connected viewer can DRIVE the session: when Claude finishes
a turn and is waiting for input, any pending viewer message is fed back as the
next instruction (decision=block), so anyone watching can answer — not just the
local user. Optionally (LIVESHORTLY_INPUT_WAIT_SECONDS > 0) the hook actively
waits a short window for a viewer to respond, notifying them it's their turn.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def _wait_seconds() -> int:
    """How long to actively wait for viewer input at end of turn (capped)."""
    try:
        n = int(os.environ.get("LIVESHORTLY_INPUT_WAIT_SECONDS", "0"))
    except ValueError:
        n = 0
    return max(0, min(n, 25))  # keep under the hook's 30s timeout


def _drive_from(comments: list) -> dict:
    """Build a Stop-hook block response that continues the session with viewer input."""
    lines = [
        "[liveshortly] A live viewer is driving the session. "
        "Address them directly (e.g. '@<handle>: …'), then continue:",
    ]
    for c in comments:
        lines.append(f"  • {c.get('username') or 'viewer'}: {c.get('message', '')}")
    return {"decision": "block", "reason": "\n".join(lines)}


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    last_message = data.get("last_assistant_message", "")
    stop_hook_active = bool(data.get("stop_hook_active"))

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        if last_message:
            common.emit_event(live_id, "response", {
                "content": common.truncate(last_message, 8000),
                "ts": common.now(),
            })

        # A viewer message already queued? Hand the turn to them immediately.
        comments = common.fetch_viewer_comments(live_id)
        if comments:
            who = ", ".join(c.get("username") or "viewer" for c in comments)
            common.notify(f"🎮 viewer input from {who} → continuing session")
            common.done(_drive_from(comments))
            return

        # Otherwise optionally wait a short window for a viewer to answer. Skip
        # when already continuing from a stop hook so we don't spin.
        wait = _wait_seconds()
        if wait and not stop_hook_active:
            common.emit_event(live_id, "input_requested", {
                "message": "Claude is waiting — send a message to steer the session.",
                "kind": "input",
                "ts": common.now(),
            })
            deadline = time.time() + wait
            while time.time() < deadline:
                time.sleep(3)
                comments = common.fetch_viewer_comments(live_id)
                if comments:
                    who = ", ".join(c.get("username") or "viewer" for c in comments)
                    common.notify(f"🎮 viewer input from {who} → continuing session")
                    common.done(_drive_from(comments))
                    return

        common.emit_event(live_id, "stream_end", {"ts": common.now()})
        common.notify("Stop — response recorded")
        common.done()
    except Exception as e:
        common.notify(f"Stop error: {e}")
        common.done()


if __name__ == "__main__":
    main()
