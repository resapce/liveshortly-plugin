#!/usr/bin/env python3
"""PreToolUse hook — shows viewers what Claude is about to do before it happens.

When a live viewer is watching, it also offers them the permission prompt: it
emits an `input_requested` event and briefly waits for a web allow/deny, then
returns that as the PreToolUse `permissionDecision`. If nobody answers in time
(or nobody is watching), it falls through to Claude Code's normal local prompt.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402

# How long to wait for a web allow/deny before falling back to the local prompt.
# Must stay below this hook's configured timeout in hooks.json.
_WAIT_SECONDS = int(os.environ.get("LIVESHORTLY_PERMISSION_WAIT", "30") or "30")
# Set LIVESHORTLY_WEB_PERMISSIONS=0 to disable web-driven approval entirely.
_WEB_PERMS = os.environ.get("LIVESHORTLY_WEB_PERMISSIONS", "1").lower() not in (
    "0", "false", "no", "off",
)
# Tools whose permission prompt we offer to the web.
_GATED_TOOLS = ("Edit", "Write", "MultiEdit", "Bash")

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


def _describe(tool_name: str, tool_input: dict) -> str:
    """One-line description of the pending action for the permission banner."""
    if tool_name == "Bash":
        return f"Run command: {common.truncate(tool_input.get('command', ''), 200)}"
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("new_path")
        or ""
    )
    verb = "Create" if tool_name == "Write" else "Edit"
    return f"{verb} file: {file_path}"


def _await_web_permission(live_id: str, tool_name: str, tool_input: dict):
    """Block briefly for a viewer's allow/deny. Returns 'allow'|'deny'|None.

    None means nobody was watching or nobody answered in time — defer to the
    normal local prompt.
    """
    if not _WEB_PERMS or tool_name not in _GATED_TOOLS:
        return None
    # A first read tells us if anyone is watching (and clears any stale answer).
    _, watchers = common.get_decision(live_id)
    if watchers < 1:
        return None

    common.emit_event(live_id, "input_requested", {
        "message": _describe(tool_name, tool_input),
        "kind":    "permission",
        "ts":      common.now(),
    })
    common.notify(f"awaiting web permission for {tool_name} ({watchers} watching)…")

    deadline = time.time() + _WAIT_SECONDS
    while time.time() < deadline:
        decision, _ = common.get_decision(live_id)
        if decision in ("allow", "deny"):
            common.notify(f"web permission → {decision}")
            return decision
        time.sleep(1.0)
    common.notify("no web answer; deferring to local prompt")
    return None


def _decision_output(decision: str) -> dict:
    """Wrap an allow/deny into a PreToolUse permissionDecision response."""
    reason = (
        "Approved by a live viewer on LiveShortly"
        if decision == "allow"
        else "Denied by a live viewer on LiveShortly"
    )
    return {
        "hookSpecificOutput": {
            "hookEventName":           "PreToolUse",
            "permissionDecision":      decision,
            "permissionDecisionReason": reason,
        }
    }


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

        # If a viewer is watching, let them answer the permission prompt from the
        # web; otherwise fall through to Claude Code's normal local prompt.
        decision = _await_web_permission(live_id, tool_name, tool_input)
        if decision in ("allow", "deny"):
            common.done(_decision_output(decision))
            return

        common.done()
    except Exception as e:
        common.notify(f"PreToolUse error: {e}")
        common.done()


if __name__ == "__main__":
    main()
