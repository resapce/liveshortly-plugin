#!/usr/bin/env python3
"""SessionStart hook — creates a live session and injects the viewer URL into Claude's context."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    cwd = data.get("cwd", "")

    common.notify("SessionStart — starting live session…")

    try:
        live_id = common.live_start(timeout=25)
        if not live_id:
            common.notify("⚠ Could not start live session (is the API running?)")
            common.done()
            return

        def _update(s):
            s["live_session_id"] = live_id
            s["cwd"] = cwd
            s["started_at"] = common.now()

        state.with_locked_state(session_id, _update)
        state.set_current_live_session(live_id)

        frontend_url = (
            os.environ.get("LIVESHORTLY_FRONTEND_URL")
            or os.environ.get("LEMMAY_FRONTEND_URL")
            or "http://localhost:3000"
        )
        live_url = f"{frontend_url}/live/{live_id}"
        common.notify(f"🔴 Recording live → {live_url}")

        common.done({
            "systemMessage": (
                f"You are live-streaming on 😍liveshortly. "
                f"Viewers are watching at: {live_url} — "
                f"acknowledge viewer messages when they arrive and keep coding."
            ),
        })
    except Exception as e:
        common.notify(f"SessionStart error: {e}")
        common.done()


if __name__ == "__main__":
    main()
