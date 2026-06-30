#!/usr/bin/env python3
"""Stop hook — records Claude's response and signals turn completion to live viewers."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    last_message = data.get("last_assistant_message", "")

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        # Report the true model once the transcript reveals it (a fresh session
        # is created before any assistant turn, so it starts model-less).
        if not s.get("model"):
            model = common.detect_model(data.get("transcript_path", ""))
            if model and common.report_model(live_id, model):
                def _set_model(st):
                    st["model"] = model
                state.with_locked_state(session_id, _set_model)
                common.notify(f"model reported → {model}")

        if last_message:
            common.emit_event(live_id, "response", {
                "content": common.truncate(last_message, 8000),
                "ts": common.now(),
            })

        common.emit_event(live_id, "stream_end", {"ts": common.now()})
        common.notify("Stop — response recorded")
        common.done()
    except Exception as e:
        common.notify(f"Stop error: {e}")
        common.done()


if __name__ == "__main__":
    main()
