# AI Shared Memory

One local place to remember what you did in Cursor, VS Code, or any AI assistant. Switch tools and paste **one block of context** instead of re-explaining everything.

- **All data stays on your computer** (`~/.ai-shared-memory/memory.db`)
- **Each git repo / folder is its own “project”** — you usually **don’t need `--project`**

---

## Setup (first time only)

```bash
cd path/to/this/repo
python3 memory_cli.py install
python3 memory_cli.py init
```

Put the command on your PATH (add to `~/.zshrc` or `~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Open a **new** terminal, then you can run `aimemory` from anywhere.

---

## Daily use (3 commands)

**1. From your code project folder**, start watching Cursor (picks up chat transcripts automatically):

```bash
cd ~/your-real-project
aimemory watch-cursor
```

Leave this terminal open while you work.

**2. When you open another AI (Claude, Copilot, Cursor again, etc.)**, copy your shared memory:

```bash
cd ~/your-real-project
aimemory context
```

Paste the output as the first message or “context” in the new tool.

**3. If something important isn’t captured automatically**, save one line:

```bash
aimemory save-event -c "Decided: use Postgres, not SQLite for prod"
```

Optional: `-y decision` or `-y goal` instead of the default note (`-y` = memory **type**).

---

## How the app knows which project you mean

Order of priority:

1. `aimemory context -p my-name` (manual)
2. Environment variable `export AI_MEMORY_PROJECT=my-name`
3. **Git repo folder name** (if you’re inside a git repo)
4. **Current folder name**

So: **always `cd` into your real project** before `watch-cursor` / `context` / `save-event`.

---

## All commands (short)

| Command | What it does |
|--------|----------------|
| `install` | Creates `~/.local/bin/aimemory` |
| `init` | Creates the database |
| `watch-cursor` | Keeps importing Cursor transcripts |
| `context` | **Paste-ready** text for your next AI |
| `recall` | Same data as JSON (for scripts) |
| `save-event` | Save a line of memory (`-c "..."`) |
| `add-task` / `update-task` | Optional task list |

Help: `aimemory -h` and `aimemory context -h`.

---

## What is automatic today?

| Tool | Automatic? |
|------|------------|
| **Cursor** | Yes — use `watch-cursor` |
| **VS Code Claude / Copilot** | Not yet — use `save-event` or future adapters |

---

## Optional: custom database path

```bash
export AI_MEMORY_DB_PATH="$HOME/Documents/my-memory.db"
```

---

## Security

- Memory is **only on your machine**.
- Don’t paste API keys or passwords into `save-event`; add filters later if you need them.

---

## Roadmap

- VS Code / Copilot adapters
- Strip secrets before save
- Smarter summaries for long histories
