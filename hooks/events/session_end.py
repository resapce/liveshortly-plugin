#!/usr/bin/env python3
"""SessionEnd hook — archives the live session as a trace when Claude Code exits."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")

    common.notify("SessionEnd — archiving session…")

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        trace_url = common.live_stop(live_id, timeout=25)

        def _clear(st):
            st.pop("live_session_id", None)

        state.with_locked_state(session_id, _clear)
        state.clear_current_live_session()

        if trace_url:
            print(f"\n[liveshortly] Session archived → {trace_url}\n", file=sys.stderr)

        common.done()
    except Exception as e:
        common.notify(f"SessionEnd error: {e}")
        common.done()


if __name__ == "__main__":
    main()
