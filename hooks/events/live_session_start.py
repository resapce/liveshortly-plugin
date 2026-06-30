#!/usr/bin/env python3
"""SessionStart hook — creates a live session and injects the viewer URL into Claude's context."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402
import auth    # noqa: E402


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    cwd = data.get("cwd", "")
    source = data.get("source") or "startup"
    # On resume the transcript already names the model; on a fresh start it's
    # unknown until the first turn (reported later from stop.py).
    model = common.detect_model(data.get("transcript_path", ""))

    base = os.path.basename(os.path.normpath(cwd)) if cwd else "session"
    if not base or base in (".", "/"):
        base = "session"
    title = f"{base} ({source})"

    # Capture requires a signed-in user (the session is owned by that account).
    if auth.access_token() is None:
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        common.notify(
            "Not signed in — run the `login` tool or "
            f"`python3 {os.path.join(plugin_root, 'lib', 'auth.py')} login`"
        )
        common.done()
        return

    common.notify("SessionStart — starting live session…")

    try:
        live_id = common.live_start(title=title, model=model, timeout=25)
        if not live_id:
            common.notify("⚠ Could not start live session (is the API running?)")
            common.done()
            return

        def _update(s):
            s["live_session_id"] = live_id
            s["cwd"] = cwd
            s["started_at"] = common.now()
            if model:
                s["model"] = model

        state.with_locked_state(session_id, _update)
        state.set_current_live_session(live_id)

        live_url = f"{common.web_url()}/session/{live_id}"
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
