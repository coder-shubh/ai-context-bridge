# Local Shared AI Memory

This project gives you one shared memory on your machine, so you can switch between tools (Cursor, Claude in VS Code, Copilot workflows, etc.) and continue from previous context.

All data is stored only on local system storage.

## Storage Location

- Default DB path: `~/.ai-shared-memory/memory.db`
- Optional override: set `AI_MEMORY_DB_PATH`

## Quick Start

1. Install global command + initialize local DB:

```bash
python3 memory_cli.py install
python3 memory_cli.py init
```

If needed, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

2. Start automatic import from Cursor transcripts:

```bash
aimemory auto-import-cursor --project my-app --watch
```

This continuously imports Cursor chat transcript entries into the shared memory DB.

3. Save memory events manually from any tool session (optional but useful for non-Cursor tools):

```bash
python3 memory_cli.py save-event \
  --project my-app \
  --tool cursor \
  --type decision \
  --content "Use Redis cache for response speed" \
  --metadata '{"files":["server/cache.ts"],"branch":"feature/cache"}'
```

4. Track open tasks:

```bash
python3 memory_cli.py add-task \
  --project my-app \
  --tool claude-vscode \
  --title "Add retry logic for API client" \
  --status in_progress
```

5. Recall context when starting another tool:

```bash
python3 memory_cli.py recall --project my-app --pretty-context
```

## Suggested Tool Workflow

- Start one terminal watcher:
  - `aimemory auto-import-cursor --project my-app --watch`
- Before starting a new AI tool session:
  - run `aimemory recall --project my-app --pretty-context`
  - paste output as first context in the new tool
- During session (especially for tools without transcript access):
  - save key decisions/goals/changes with `aimemory save-event`
- When tasks move:
  - use `aimemory add-task` and `aimemory update-task`

## Event Types (recommended)

- `goal`: current objective
- `decision`: architecture or approach decisions
- `change`: important code changes
- `note`: extra context

## Commands

- `init`
- `install`
- `save-event`
- `add-task`
- `update-task`
- `recall`
- `auto-import-cursor`

Run help:

```bash
python3 memory_cli.py -h
python3 memory_cli.py recall -h
```

or after install:

```bash
aimemory -h
```

## Current Auto-Capture Coverage

- Automatic now: Cursor transcript ingestion (`auto-import-cursor`)
- For VS Code Claude / GitHub Copilot:
  - there is no stable universal OS-level API to capture every chat automatically from all tools
  - use `save-event` or add tool-specific adapter scripts/extensions next

## Security Notes

- This is local-first and stores memory on your machine only.
- Still avoid storing secrets in event content.
- You can later add content filters for API keys and `.env` patterns.
