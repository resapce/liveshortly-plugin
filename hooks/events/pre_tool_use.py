#!/usr/bin/env python3
"""PreToolUse hook — shows viewers what Claude is about to do before it happens."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402

_DANGER = [
    r'\brm\s+-[rf]{1,2}\b',
    r'\bdrop\s+table\b',
    r'\btruncate\b',
    r'\bgit\s+(push\s+.*--force|reset\s+--hard)\b',
    r'\bpkill\b',
    r'\bkill\s+-9\b',
    r'\bchmod\s+777\b',
    r'\bmkfs\b',
    r'\bdd\s+if=\b',
]


def _is_dangerous(cmd: str) -> bool:
    low = cmd.lower()
    return any(re.search(p, low) for p in _DANGER)


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    tool_name  = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    try:
        s = state.load(session_id)
        live_id = s.get("live_session_id")
        if not live_id:
            common.done()
            return

        if tool_name in ("Edit", "Write", "MultiEdit"):
            file_path = (
                tool_input.get("file_path")
                or tool_input.get("path")
                or tool_input.get("new_path")
                or ""
            )
            common.emit_event(live_id, "pre_tool", {
                "tool":   tool_name,
                "action": "editing",
                "file":   file_path,
                "ts":     common.now(),
            })
            common.notify(f"PreToolUse({tool_name}) → {file_path}")

        elif tool_name == "Bash":
            command   = tool_input.get("command", "")
            dangerous = _is_dangerous(command)
            common.emit_event(live_id, "pre_tool", {
                "tool":      "Bash",
                "action":    "running",
                "command":   common.truncate(command, 300),
                "dangerous": dangerous,
                "ts":        common.now(),
            })
            flag = "⚠ DANGER" if dangerous else "ok"
            common.notify(f"PreToolUse(Bash) [{flag}] → {common.truncate(command, 80)}")

        elif tool_name == "WebFetch":
            url = tool_input.get("url", "")
            common.emit_event(live_id, "pre_tool", {
                "tool":   "WebFetch",
                "action": "fetching",
                "url":    url,
                "ts":     common.now(),
            })

        common.done()
    except Exception as e:
        common.notify(f"PreToolUse error: {e}")
        common.done()


if __name__ == "__main__":
    main()
