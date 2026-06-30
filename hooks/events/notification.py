#!/usr/bin/env python3
"""Notification hook — surfaces "Claude is waiting" / permission prompts to viewers.

Claude Code fires Notification when it needs the developer's attention: a tool
permission prompt ("Claude needs your permission to use Bash") or an idle input
wait ("Claude is waiting for your input"). We emit an `input_requested` event so
the web viewer shows a banner and lets any commenter answer — their reply is
queued and injected on the next prompt/tool boundary.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def _classify(message: str) -> str:
    low = (message or "").lower()
    if "permission" in low or "approve" in low or "allow" in low:
        return "permission"
    return "input"


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    message = (data.get("message") or "Claude is waiting for your input").strip()

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        kind = _classify(message)
        common.emit_event(live_id, "input_requested", {
            "message": common.truncate(message, 500),
            "kind":    kind,
            "ts":      common.now(),
        })
        common.notify(f"Notification [{kind}] → web: {common.truncate(message, 80)}")
        common.done()
    except Exception as e:
        common.notify(f"Notification error: {e}")
        common.done()


if __name__ == "__main__":
    main()
