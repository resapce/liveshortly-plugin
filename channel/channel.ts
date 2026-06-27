#!/usr/bin/env node
/**
 * liveshortly channel server
 *
 * Two-way webhook bridge + live viewer comment poller:
 *   POST /          → push message to Claude as a channel event
 *   GET  /events    → SSE stream of Claude's replies + permission prompts
 *
 * Comment poller: reads ~/.claude/liveshortly/current.json for the active live
 * session ID, then polls GET /api/live/:id/comments/pending every COMMENT_POLL_MS
 * milliseconds and pushes any pending comments to Claude as channel notifications.
 *
 * Env vars:
 *   CHANNEL_PORT        HTTP port (default 8788)
 *   ALLOWED_SENDERS     Comma-separated sender allowlist (default "dev")
 *   LIVESHORTLY_API_URL API base URL (default http://localhost:8000)
 *   LEMMAY_API_URL      Fallback API base URL
 *   COMMENT_POLL_MS     Polling interval in ms (default 3000)
 *
 * Test (three terminals):
 *   Terminal 1: claude --plugin-dir . --dangerously-load-development-channels plugin:liveshortly@liveshortly-local
 *   Terminal 2: curl -N localhost:8788/events
 *   Terminal 3: curl -d "list files here" -H "X-Sender: dev" localhost:8788
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js'
// reply tool disabled — kept for future re-enable
import { createServer, IncomingMessage, ServerResponse } from 'http'
import { readFileSync } from 'fs'
import { execSync } from 'child_process'
import { z } from 'zod'

// ─── config ───────────────────────────────────────────────────────────────────

const PORT = Number(process.env.CHANNEL_PORT ?? 8788)
const ALLOWED_SENDERS = new Set(
  (process.env.ALLOWED_SENDERS ?? 'dev').split(',').map(s => s.trim())
)
const API_URL = (
  process.env.LIVESHORTLY_API_URL ??
  process.env.LEMMAY_API_URL ??
  'http://localhost:8000'
).replace(/\/$/, '')
const POLL_INTERVAL_MS = Number(process.env.COMMENT_POLL_MS ?? 3000)
const HOME = process.env.HOME ?? process.env.USERPROFILE ?? ''
const CURRENT_FILE = `${HOME}/.claude/liveshortly/current.json`

function log(msg: string) {
  process.stderr.write(`[liveshortly-channel] ${msg}\n`)
}

// kill any stale process holding our port so reconnects always succeed
try {
  execSync(`lsof -ti :${PORT} | xargs kill -9 2>/dev/null || true`, { stdio: 'ignore' })
  await new Promise(r => setTimeout(r, 150))
} catch { /* ignore */ }

// ─── SSE broadcast ────────────────────────────────────────────────────────────

const listeners = new Set<(chunk: string) => void>()

function broadcast(text: string) {
  const chunk = text.split('\n').map(l => `data: ${l}\n`).join('') + '\n'
  for (const emit of listeners) emit(chunk)
}

// ─── MCP server ───────────────────────────────────────────────────────────────

const mcp = new Server(
  { name: 'liveshortly-channel', version: '2.0.0' },
  {
    capabilities: {
      experimental: {
        'claude/channel': {},
        'claude/channel/permission': {},
      },
      tools: {},
    },
    instructions:
      'Messages arrive as <channel source="liveshortly-channel" chat_id="...">. ' +
      'Read viewer comments and respond to them inline in your current work.',
  },
)

// ─── tools (none active) ─────────────────────────────────────────────────────

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [] }))
mcp.setRequestHandler(CallToolRequestSchema, async req => {
  throw new Error(`unknown tool: ${req.params.name}`)
})

// ─── permission relay ─────────────────────────────────────────────────────────

const PermissionRequestSchema = z.object({
  method: z.literal('notifications/claude/channel/permission_request'),
  params: z.object({
    request_id:    z.string(),
    tool_name:     z.string(),
    description:   z.string(),
    input_preview: z.string(),
  }),
})

mcp.setNotificationHandler(PermissionRequestSchema, async ({ params }) => {
  broadcast(
    `[permission] Claude wants to run ${params.tool_name}: ${params.description}\n` +
    `Reply "yes ${params.request_id}" or "no ${params.request_id}"`,
  )
})

// ─── connect to Claude Code over stdio ───────────────────────────────────────

await mcp.connect(new StdioServerTransport())

// ─── comment poller ───────────────────────────────────────────────────────────

let nextId = 1

function readCurrentLiveId(): string | null {
  try {
    const raw = readFileSync(CURRENT_FILE, 'utf8')
    return (JSON.parse(raw) as { live_session_id?: string })?.live_session_id ?? null
  } catch {
    return null
  }
}

async function pollComments() {
  const liveId = readCurrentLiveId()
  if (!liveId) return

  let data: { comments?: { username?: string; message?: string; id?: string }[] }
  try {
    const resp = await fetch(`${API_URL}/api/live/${liveId}/comments/pending`)
    if (!resp.ok) return
    data = await resp.json() as typeof data
  } catch {
    return // API not running — skip silently
  }

  for (const comment of (data.comments ?? [])) {
    const username = comment.username ?? 'viewer'
    const message  = comment.message  ?? ''
    const chat_id  = String(nextId++)
    log(`viewer comment from ${username}: ${message}`)
    try {
      await mcp.notification({
        method: 'notifications/claude/channel',
        params: {
          content: `${username}: ${message}`,
          meta: { chat_id, source: 'viewer-comment', live_session_id: liveId },
        },
      })
    } catch (err) {
      log(`failed to push comment: ${err}`)
    }
  }
}

setInterval(pollComments, POLL_INTERVAL_MS)
log(`comment poller started (interval: ${POLL_INTERVAL_MS}ms, api: ${API_URL})`)

// ─── HTTP server ──────────────────────────────────────────────────────────────

const VERDICT_RE = /^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$/i

async function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = ''
    req.on('data', chunk => { body += chunk })
    req.on('end', () => resolve(body))
    req.on('error', reject)
  })
}

createServer(async (req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${PORT}`)

  // GET /events — SSE stream for replies and permission prompts
  if (req.method === 'GET' && url.pathname === '/events') {
    res.writeHead(200, {
      'Content-Type':  'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection:      'keep-alive',
    })
    res.write(': connected\n\n')
    const emit = (chunk: string) => res.write(chunk)
    listeners.add(emit)
    req.on('close', () => listeners.delete(emit))
    return
  }

  // gate on sender
  const sender = (req.headers['x-sender'] as string) ?? ''
  if (!ALLOWED_SENDERS.has(sender)) {
    res.writeHead(403).end('forbidden')
    return
  }

  const body = await readBody(req)

  // verdict? route to permission relay
  const m = VERDICT_RE.exec(body)
  if (m) {
    await mcp.notification({
      method: 'notifications/claude/channel/permission',
      params: {
        request_id: m[2]!.toLowerCase(),
        behavior:   m[1]!.toLowerCase().startsWith('y') ? 'allow' : 'deny',
      },
    })
    res.writeHead(200).end('verdict recorded')
    return
  }

  // normal message → push to Claude
  const chat_id = String(nextId++)
  await mcp.notification({
    method: 'notifications/claude/channel',
    params: { content: body, meta: { chat_id, path: url.pathname } },
  })
  res.writeHead(200).end('ok')

}).listen(PORT, '127.0.0.1', () => {
  log(`listening on http://127.0.0.1:${PORT} (senders: ${[...ALLOWED_SENDERS].join(', ')})`)
})
