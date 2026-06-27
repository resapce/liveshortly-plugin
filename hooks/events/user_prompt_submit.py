#!/usr/bin/env python3
"""UserPromptSubmit hook — emits the user prompt to the live feed and injects viewer comments."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402


_CHANNEL_TAG_RE = re.compile(r'<channel\s[^>]*liveshortly[^>]*>.*?</channel>', re.DOTALL | re.IGNORECASE)

def _is_channel_turn(text: str) -> bool:
    return bool(_CHANNEL_TAG_RE.search(text)) and not _CHANNEL_TAG_RE.sub('', text).strip()


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    prompt_text = data.get("prompt", "")

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")

        if not live_id:
            common.done()
            return

        if _is_channel_turn(prompt_text):
            common.done()
            return

        common.emit_event(live_id, "prompt", {
            "content": common.truncate(prompt_text, 4000),
            "ts": common.now(),
        })
        common.notify("UserPromptSubmit — prompt recorded")

        comments = common.fetch_viewer_comments(live_id)
        if comments:
            who_list = ", ".join(c.get("username") or "viewer" for c in comments)
            common.notify(f"💬 {len(comments)} viewer comment(s) from {who_list} → injected")
            context_lines = ["[liveshortly] Live viewer message(s) (respond if relevant):"]
            for c in comments:
                context_lines.append(f"  • {c.get('username') or 'viewer'}: {c.get('message', '')}")
            common.done({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "\n".join(context_lines),
                }
            })
        else:
            common.done()

    except Exception as e:
        common.notify(f"UserPromptSubmit error: {e}")
        common.done()


if __name__ == "__main__":
    main()
