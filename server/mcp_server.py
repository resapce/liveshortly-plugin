#!/usr/bin/env python3
"""MCP server for the liveshortly plugin.

Tools:
  search_traces  — search recorded AI sessions by keyword
  get_trace      — fetch full conversation + tool calls from a trace
  get_feed       — browse trending / latest / most-forked sessions
  fork_trace     — fork a trace to create your own copy
"""
from __future__ import annotations  # PEP 604 (dict | None) on Python 3.9

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = (
    os.environ.get("LIVESHORTLY_API_URL")
    or os.environ.get("LEMMAY_API_URL")
    or "http://localhost:8000"
).rstrip("/")


def _get(path: str) -> dict:
    with urllib.request.urlopen(API_URL + path, timeout=15) as r:
        return json.loads(r.read())


def _post(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(API_URL + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# ── formatters ────────────────────────────────────────────────────────────────

def _fmt_trace(t: dict) -> str:
    parts = [f"[{t['id']}] {t.get('title', '(untitled)')}"]
    if t.get("username"):
        parts.append(f"  author: @{t['username']}")
    if t.get("model"):
        parts.append(f"  model: {t['model']}")
    parts.append(f"  views: {t.get('view_count', 0)}  forks: {t.get('fork_count', 0)}")
    if t.get("tags"):
        parts.append(f"  tags: {', '.join(t['tags'])}")
    if t.get("description"):
        parts.append(f"  {t['description']}")
    return "\n".join(parts)


def _fmt_event(e: dict) -> str:
    p = e.get("payload") or {}
    et = e.get("event_type", "")
    if et == "prompt":
        return f"USER: {str(p.get('content', ''))[:300]}"
    if et == "response":
        return f"CLAUDE: {str(p.get('content', ''))[:300]}"
    if et == "tool_call":
        detail = p.get("command") or p.get("file") or json.dumps(p)[:120]
        return f"TOOL({p.get('tool', '?')}): {detail}"
    if et == "file_write":
        return f"WRITE: {p.get('file', '?')}"
    if et == "viewer_comment":
        return f"VIEWER @{p.get('username', '?')}: {p.get('message', '')}"
    return f"[{et}]"


# ── tool registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_traces",
        "description": "Search recorded AI agent sessions by keyword. Returns matching traces with IDs you can pass to get_trace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords, e.g. \"rust auth\", \"kubernetes debug\""},
                "tags":  {"type": "array", "items": {"type": "string"}, "description": "Filter by tags, e.g. [\"rust\", \"auth\"]"},
                "model": {"type": "string", "description": "Filter by model name, e.g. \"claude-sonnet-4\""},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10, "description": "Max results (1–50)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_trace",
        "description": "Retrieve the full conversation history and tool calls from a trace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id":           {"type": "string", "description": "Trace ID from search_traces or the URL /trace/<id>"},
                "events_limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50, "description": "Max events to return"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "get_feed",
        "description": "Browse the feed: trending, latest, or most-forked AI agent sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type":  {"type": "string", "enum": ["trending", "latest", "forked"], "default": "trending",
                          "description": "Feed type: trending (views+forks, last 7 days), latest, forked"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "fork_trace",
        "description": "Fork a trace to create your own copy. Preserves all events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "ID of the trace to fork"},
            },
            "required": ["trace_id"],
        },
    },
]


# ── tool handlers ─────────────────────────────────────────────────────────────

def handle_search_traces(args: dict) -> str:
    query = args.get("query", "")
    limit = args.get("limit", 10)
    qs = urllib.parse.urlencode({
        "q":     query,
        "limit": limit,
        **({"tags":  ",".join(args["tags"])} if args.get("tags")  else {}),
        **({"model": args["model"]}           if args.get("model") else {}),
    })
    data = _get(f"/api/search?{qs}")
    results = data.get("results", [])
    total   = data.get("total", len(results))
    if not results:
        return f'No traces found for "{query}".'
    lines = [_fmt_trace(t) for t in results]
    return f'{total} result{"s" if total != 1 else ""} for "{query}" (showing {len(results)}):\n\n' + "\n\n".join(lines)


def handle_get_trace(args: dict) -> str:
    trace_id     = args["id"]
    events_limit = args.get("events_limit", 50)
    trace  = _get(f"/api/traces/{trace_id}")
    events = (trace.get("events") or [])[:events_limit]
    meta = "\n".join(filter(None, [
        f"TRACE: {trace.get('title', '(untitled)')}",
        f"ID: {trace['id']}",
        f"Author: @{trace.get('username', 'unknown')}",
        f"Model: {trace.get('model', 'unknown')}",
        f"Tags: {', '.join(trace.get('tags') or []) or 'none'}",
        f"Views: {trace.get('view_count', 0)}  Forks: {trace.get('fork_count', 0)}",
        f"Forked from: {trace['fork_of']}" if trace.get("fork_of") else None,
        f"Description: {trace.get('description') or 'none'}",
        f"Events: {len(trace.get('events') or [])} total (showing {len(events)})",
    ]))
    event_text = "\n".join(_fmt_event(e) for e in events) or "(no events)"
    return f"{meta}\n\n{'─' * 60}\n\n{event_text}"


def handle_get_feed(args: dict) -> str:
    feed_type = args.get("type", "trending")
    limit     = args.get("limit", 10)
    data    = _get(f"/api/feed?type={feed_type}")
    results = (data.get("results") or [])[:limit]
    if not results:
        return "No traces in feed yet."
    lines = [_fmt_trace(t) for t in results]
    return f"{feed_type} feed ({len(results)} traces):\n\n" + "\n\n".join(lines)


def handle_fork_trace(args: dict) -> str:
    trace_id = args["trace_id"]
    data = _post(f"/api/fork/{trace_id}")
    new_id = data.get("trace_id", "?")
    frontend = (
        os.environ.get("LIVESHORTLY_WEB_URL")
        or os.environ.get("LIVESHORTLY_FRONTEND_URL")
        or os.environ.get("LEMMAY_FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"Forked successfully.\nNew trace ID: {new_id}\nView at: {frontend}/trace/{new_id}"


HANDLERS = {
    "search_traces": handle_search_traces,
    "get_trace":     handle_get_trace,
    "get_feed":      handle_get_feed,
    "fork_trace":    handle_fork_trace,
}


# ── JSON-RPC plumbing ─────────────────────────────────────────────────────────

def _respond(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(req: dict) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return _respond(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "liveshortly-server", "version": "2.1.0"},
        })

    if method in ("notifications/initialized", "ping"):
        return None

    if method == "tools/list":
        return _respond(req_id, {"tools": TOOLS})

    if method == "tools/call":
        params  = req.get("params", {})
        tool    = params.get("name")
        args    = params.get("arguments", {})
        handler = HANDLERS.get(tool)
        if not handler:
            return _error(req_id, -32601, f"Unknown tool: {tool}")
        try:
            text = handler(args)
            return _respond(req_id, {"content": [{"type": "text", "text": text}]})
        except urllib.error.HTTPError as e:
            return _error(req_id, -32603, f"API error {e.code}: {e.reason}")
        except Exception as e:
            return _error(req_id, -32603, str(e))

    if req_id is not None:
        return _error(req_id, -32601, f"Method not found: {method}")
    return None


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
