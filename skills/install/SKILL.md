---
name: install-liveshortly
description: Install, update, or uninstall the liveshortly plugin from the local marketplace. Run this skill to set up the plugin for development or production use.
---

# Install Liveshortly Plugin

Follow the steps below based on what you need.

---

## One-time dev session (no install)

Load the plugin for this session only — nothing is written to global settings:

```bash
claude --plugin-dir /Users/mukullohar/Desktop/code/liveshortly/plugin
```

Or load and enable the channel at the same time:

```bash
claude --dangerously-load-development-channels plugin:liveshortly@liveshortly-local --plugin-dir /Users/mukullohar/Desktop/code/liveshortly/plugin
```

---

## Permanent install (persists across sessions)

**Step 1 — Register the local marketplace** (only needed once):

```bash
claude plugin marketplace add /Users/mukullohar/Desktop/code/liveshortly/plugin --scope user
```

If the CLI assigned it the wrong name, patch the cache directly:

```bash
# Rename the key in the known_marketplaces cache from whatever was written to liveshortly-local
node -e "
const fs = require('fs');
const p = require('os').homedir() + '/.claude/plugins/known_marketplaces.json';
const db = JSON.parse(fs.readFileSync(p,'utf8'));
const oldKey = Object.keys(db).find(k => db[k].source?.path?.includes('liveshortly/plugin') && k !== 'liveshortly-local');
if (oldKey) { db['liveshortly-local'] = db[oldKey]; delete db[oldKey]; fs.writeFileSync(p, JSON.stringify(db, null, 2)); console.log('renamed', oldKey, '→ liveshortly-local'); }
else console.log('already correct or not found');
"
```

**Step 2 — Install the plugin**:

```bash
claude plugin install liveshortly@liveshortly-local --scope user
```

**Step 3 — Verify**:

```bash
claude plugin list
```

Expected output includes:
```
❯ liveshortly@liveshortly-local
  Version: 1.9.0
  Scope: user
  Status: ✔ enabled
```

---

## Update after code changes

```bash
claude plugin marketplace update liveshortly-local
claude plugin update liveshortly@liveshortly-local
```

---

## Enable / disable without uninstalling

```bash
# Disable
claude plugin disable liveshortly@liveshortly-local

# Re-enable
claude plugin enable liveshortly@liveshortly-local
```

---

## Uninstall

```bash
claude plugin uninstall liveshortly@liveshortly-local
```

To also remove the local marketplace registration:

```bash
claude plugin marketplace remove liveshortly-local
```

---

## Validate the plugin manifest

```bash
claude plugin validate /Users/mukullohar/Desktop/code/liveshortly/plugin
```

---

## MCP servers this plugin starts

| Server | Command | Purpose |
|--------|---------|---------|
| `liveshortly-server` | `python3 server/mcp_server.py` | Read / write the injected system message |
| `liveshortly-channel` | `bun run channel/channel.ts` | Two-way webhook channel for live viewer messages |
