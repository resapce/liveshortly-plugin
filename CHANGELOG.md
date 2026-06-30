# Changelog

All notable changes to the LiveShortly plugin are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/);
this project uses semantic-ish versioning (`MAJOR.MINOR.PATCH`).

## [3.2.0]

### Added
- **Web-driven permission decisions.** When a viewer is watching a live session,
  the web banner's **Yes/No** buttons now actually answer the CLI's permission
  prompt. The `PreToolUse` hook detects watchers, emits an `input_requested`
  (kind=permission) for the pending Edit/Write/Bash, and waits up to
  `LIVESHORTLY_PERMISSION_WAIT` seconds (default 30) for a `POST /decision`
  allow/deny, returning it as the hook's `permissionDecision`. A `viewer_decision`
  event records who answered.
- When nobody is watching (no web tab open) or nobody answers in time, the hook
  defers to Claude Code's normal local prompt — **zero added latency for solo
  local coding**. Set `LIVESHORTLY_WEB_PERMISSIONS=0` to disable entirely.

### Fixed
- Pressing Yes/No in the web previously arrived only as a chat message and could
  not drive the blocked CLI prompt; it now resolves the prompt directly.

## [3.1.0]

### Added
- **Web input/permission prompts.** A new `Notification` hook
  (`hooks/events/notification.py`) emits an `input_requested` event whenever
  Claude Code blocks for the developer — a tool permission prompt or an idle
  input wait. The web viewer surfaces it as a banner with one-tap **Yes/No**
  (permission) or **Continue** (input) quick replies plus a free-text composer;
  any reply is queued and injected on the next prompt/tool boundary.

### Changed
- **Real model name.** The capture client now reads the actual model from the
  session transcript (`message.model`, e.g. `claude-opus-4-8`) and reports it
  via `PATCH /api/sessions/{id}` instead of the hardcoded `"claude"`. Resumed
  sessions report at start; fresh sessions report once the first turn reveals
  the model.

### Server-side (LiveShortly API/web, deployed separately)
- Idle live-session timeout and pending-comment TTL raised from 2h → 7h.

## [3.0.0]
- Browser-based sign-in, Drive-style session sharing, and viewer talk-back.
