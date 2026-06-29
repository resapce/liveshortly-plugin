#!/usr/bin/env python3
"""Notification hook — tells live viewers that Claude is waiting for input.

Claude Code fires Notification when it needs the user's attention (a permission
prompt, or the input box sitting idle). We surface that to everyone watching the
live session as an `input_requested` event so the web can show a banner + push a
browser notification, and any connected viewer can answer.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    message = (data.get("message") or "").strip() or "Claude is waiting for your input"

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        # Classify so the web can phrase it ("approve this?" vs "what next?").
        low = message.lower()
        kind = "permission" if ("permission" in low or "approve" in low) else "input"

        common.emit_event(live_id, "input_requested", {
            "message": common.truncate(message, 500),
            "kind": kind,
            "ts": common.now(),
        })
        common.notify(f"🔔 input requested → viewers notified: {message}")
        common.done()
    except Exception as e:
        common.notify(f"Notification error: {e}")
        common.done()


if __name__ == "__main__":
    main()
