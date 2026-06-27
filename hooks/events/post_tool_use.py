#!/usr/bin/env python3
"""PostToolUse hook — emits file edits and bash commands to the live feed."""
import difflib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import common  # noqa: E402
import state   # noqa: E402

MAX_DIFF_LINES = 120


def compute_diff(file_path: str, old: str, new: str) -> tuple[str, int, int]:
    """Return (unified_diff_str, added_count, removed_count)."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=file_path, tofile=file_path,
        n=2,
    ))
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        diff_lines.append(f"\\ ... diff truncated at {MAX_DIFF_LINES} lines\n")
    added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))
    return ''.join(diff_lines), added, removed


def compute_write_diff(file_path: str, content: str) -> tuple[str, int, int]:
    """For Write tool — show full new content as added lines."""
    lines = content.splitlines(keepends=True)
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES]
    diff = f"+++ {file_path} (new file)\n" + ''.join(f"+{l}" for l in lines)
    return diff, len(lines), 0


def main():
    data = common.read_stdin()
    session_id = data.get("session_id", "default")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}

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
            diff = ""
            added = 0
            removed = 0

            if tool_name == "Edit":
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                diff, added, removed = compute_diff(file_path, old, new)

            elif tool_name == "Write":
                content = tool_input.get("content", "")
                diff, added, removed = compute_write_diff(file_path, content)

            elif tool_name == "MultiEdit":
                edits = tool_input.get("edits") or []
                combined_diff = []
                total_added = 0
                total_removed = 0
                for edit in edits:
                    d, a, r = compute_diff(file_path, edit.get("old_string", ""), edit.get("new_string", ""))
                    combined_diff.append(d)
                    total_added += a
                    total_removed += r
                diff = "\n".join(combined_diff)
                added = total_added
                removed = total_removed

            payload = {
                "tool": tool_name,
                "file": file_path,
                "diff": diff,
                "added": added,
                "removed": removed,
                "ts": common.now(),
            }
            common.emit_event(live_id, "file_write", payload)
            common.notify(f"PostToolUse({tool_name}) — {file_path} +{added} -{removed}")

        elif tool_name == "Bash":
            command = tool_input.get("command", "")
            stdout_snip = ""
            if isinstance(tool_response, dict):
                stdout_snip = common.truncate(tool_response.get("stdout", ""), 300)
            elif isinstance(tool_response, str):
                stdout_snip = common.truncate(tool_response, 300)
            common.emit_event(live_id, "tool_call", {
                "tool": "Bash",
                "command": common.truncate(command, 500),
                "output": stdout_snip,
                "ts": common.now(),
            })
            common.notify("PostToolUse(Bash)")

        common.done()
    except Exception as e:
        common.notify(f"PostToolUse error: {e}")
        common.done()


if __name__ == "__main__":
    main()
