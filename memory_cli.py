#!/usr/bin/env python3
"""
Local-first shared memory CLI for cross-tool AI continuity.

Stores all data in local system storage:
  ~/.ai-shared-memory/memory.db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


APP_DIR = Path.home() / ".ai-shared-memory"
DB_PATH = APP_DIR / "memory.db"
LOCAL_BIN_DIR = Path.home() / ".local" / "bin"
CURSOR_PROJECTS_DIR = Path.home() / ".cursor" / "projects"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> Path:
    # Allow explicit override but default to true local system storage.
    custom_path = os.environ.get("AI_MEMORY_DB_PATH")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    return DB_PATH


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open', 'in_progress', 'done')),
                source_tool TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_project_time
                ON events(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status
                ON tasks(project_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS imported_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL UNIQUE,
                tool_name TEXT NOT NULL,
                project_id TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            """
        )


def save_event(args: argparse.Namespace) -> None:
    init_db()

    metadata: Dict[str, Any] = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in --metadata: {exc}") from exc

    created_at = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO events(project_id, tool_name, event_type, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                args.project,
                args.tool,
                args.type,
                args.content,
                json.dumps(metadata, ensure_ascii=True),
                created_at,
            ),
        )

    print(
        json.dumps(
            {
                "ok": True,
                "action": "save_event",
                "project": args.project,
                "tool": args.tool,
                "event_type": args.type,
                "created_at": created_at,
            },
            indent=2,
        )
    )


def add_task(args: argparse.Namespace) -> None:
    init_db()
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks(project_id, title, status, source_tool, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (args.project, args.title, args.status, args.tool, now, now),
        )
        task_id = cursor.lastrowid

    print(
        json.dumps(
            {
                "ok": True,
                "action": "add_task",
                "task_id": task_id,
                "project": args.project,
                "status": args.status,
            },
            indent=2,
        )
    )


def update_task(args: argparse.Namespace) -> None:
    init_db()
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (args.status, now, args.id, args.project),
        )
        if cursor.rowcount == 0:
            raise SystemExit(
                f"Task {args.id} not found for project '{args.project}'."
            )

    print(
        json.dumps(
            {
                "ok": True,
                "action": "update_task",
                "task_id": args.id,
                "project": args.project,
                "status": args.status,
            },
            indent=2,
        )
    )


def recall(args: argparse.Namespace) -> None:
    init_db()
    with get_conn() as conn:
        events = conn.execute(
            """
            SELECT id, tool_name, event_type, content, metadata_json, created_at
            FROM events
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit_events),
        ).fetchall()

        tasks = conn.execute(
            """
            SELECT id, title, status, source_tool, updated_at
            FROM tasks
            WHERE project_id = ?
              AND status IN ('open', 'in_progress')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit_tasks),
        ).fetchall()

    normalized_events: List[Dict[str, Any]] = []
    for row in events:
        try:
            metadata = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            metadata = {}
        normalized_events.append(
            {
                "id": row["id"],
                "tool": row["tool_name"],
                "type": row["event_type"],
                "content": row["content"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )

    normalized_tasks = [
        {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "source_tool": row["source_tool"],
            "updated_at": row["updated_at"],
        }
        for row in tasks
    ]

    output = {
        "project": args.project,
        "memory_db": str(get_db_path()),
        "open_tasks": normalized_tasks,
        "recent_events": normalized_events,
    }

    if args.pretty_context:
        print(render_context_text(output))
    else:
        print(json.dumps(output, indent=2))


def install_command(_args: argparse.Namespace) -> None:
    init_db()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve()
    launcher_path = LOCAL_BIN_DIR / "aimemory"
    launcher_content = (
        "#!/usr/bin/env bash\n"
        f"python3 \"{script_path}\" \"$@\"\n"
    )
    launcher_path.write_text(launcher_content, encoding="ascii")
    launcher_path.chmod(0o755)

    print(
        json.dumps(
            {
                "ok": True,
                "action": "install",
                "launcher": str(launcher_path),
                "db": str(get_db_path()),
                "next": [
                    "Ensure ~/.local/bin is in PATH",
                    "Run: aimemory auto-import-cursor --project <name> --watch",
                ],
            },
            indent=2,
        )
    )


def parse_json_line(line: str) -> Dict[str, Any]:
    try:
        item = json.loads(line)
        if isinstance(item, dict):
            return item
    except json.JSONDecodeError:
        pass
    return {}


def extract_text_from_event(event: Dict[str, Any]) -> str:
    candidate_keys = ["content", "text", "message", "prompt", "response", "body"]
    for key in candidate_keys:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(event.get("parts"), list):
        parts = [p for p in event["parts"] if isinstance(p, str) and p.strip()]
        if parts:
            return " | ".join(parts)
    return ""


def source_fingerprint(tool_name: str, file_path: Path, line_index: int) -> str:
    raw = f"{tool_name}:{file_path.resolve()}:{line_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def was_imported(conn: sqlite3.Connection, source_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM imported_sources WHERE source_id = ? LIMIT 1",
        (source_id,),
    ).fetchone()
    return row is not None


def mark_imported(
    conn: sqlite3.Connection, source_id: str, tool_name: str, project_id: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO imported_sources(source_id, tool_name, project_id, imported_at)
        VALUES (?, ?, ?, ?)
        """,
        (source_id, tool_name, project_id, utc_now()),
    )


def import_cursor_transcript_file(
    conn: sqlite3.Connection, project_id: str, file_path: Path
) -> int:
    imported_count = 0
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0

    for idx, line in enumerate(content, start=1):
        if not line.strip():
            continue
        source_id = source_fingerprint("cursor", file_path, idx)
        if was_imported(conn, source_id):
            continue

        event = parse_json_line(line)
        text = extract_text_from_event(event)
        if not text:
            # Keep dedupe marker so we do not re-parse useless lines forever.
            mark_imported(conn, source_id, "cursor", project_id)
            continue

        metadata = {
            "source": "cursor_agent_transcript",
            "file": str(file_path),
            "line": idx,
        }
        conn.execute(
            """
            INSERT INTO events(project_id, tool_name, event_type, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "cursor",
                "imported_chat",
                text[:2000],
                json.dumps(metadata, ensure_ascii=True),
                utc_now(),
            ),
        )
        mark_imported(conn, source_id, "cursor", project_id)
        imported_count += 1

    return imported_count


def auto_import_cursor(args: argparse.Namespace) -> None:
    init_db()
    root = Path(args.cursor_projects_dir).expanduser()
    if not root.exists():
        raise SystemExit(f"Cursor projects directory not found: {root}")

    def run_once() -> int:
        files = sorted(root.glob("*/agent-transcripts/*.jsonl"))
        total = 0
        with get_conn() as conn:
            for file_path in files:
                total += import_cursor_transcript_file(conn, args.project, file_path)
        return total

    if args.watch:
        print(
            f"Watching Cursor transcripts in {root} every {args.interval}s for project '{args.project}'."
        )
        try:
            while True:
                imported = run_once()
                if imported:
                    print(f"[{utc_now()}] imported {imported} new entries")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped watcher.")
            return

    imported = run_once()
    print(
        json.dumps(
            {
                "ok": True,
                "action": "auto_import_cursor",
                "project": args.project,
                "imported_entries": imported,
                "cursor_projects_dir": str(root),
            },
            indent=2,
        )
    )


def render_context_text(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"Project: {payload['project']}")
    lines.append("Shared Memory Snapshot")
    lines.append("")

    open_tasks = payload.get("open_tasks", [])
    lines.append("Open Tasks:")
    if not open_tasks:
        lines.append("- none")
    else:
        for task in open_tasks:
            lines.append(
                f"- [{task['status']}] #{task['id']} {task['title']} (from {task['source_tool']})"
            )
    lines.append("")

    events = payload.get("recent_events", [])
    lines.append("Recent Events:")
    if not events:
        lines.append("- none")
    else:
        for event in events:
            lines.append(
                f"- {event['created_at']} | {event['tool']} | {event['type']} | {event['content']}"
            )
    lines.append("")
    lines.append("Use this context as the previous brain before responding.")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local shared AI memory CLI (single machine, system storage)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Initialize local memory database")
    init_cmd.set_defaults(func=lambda _args: init_db())

    install_cmd = sub.add_parser(
        "install", help="Install global 'aimemory' command in ~/.local/bin"
    )
    install_cmd.set_defaults(func=install_command)

    save_cmd = sub.add_parser("save-event", help="Save one memory event")
    save_cmd.add_argument("--project", required=True, help="Project identifier")
    save_cmd.add_argument("--tool", required=True, help="Tool name (cursor/claude/copilot)")
    save_cmd.add_argument("--type", required=True, help="Event type (goal/decision/change/note)")
    save_cmd.add_argument("--content", required=True, help="Event content")
    save_cmd.add_argument(
        "--metadata",
        default="{}",
        help='Optional JSON object, e.g. \'{"files":["app.py"],"branch":"main"}\'',
    )
    save_cmd.set_defaults(func=save_event)

    add_task_cmd = sub.add_parser("add-task", help="Add a tracked task")
    add_task_cmd.add_argument("--project", required=True, help="Project identifier")
    add_task_cmd.add_argument("--tool", required=True, help="Source tool")
    add_task_cmd.add_argument("--title", required=True, help="Task title")
    add_task_cmd.add_argument(
        "--status", choices=["open", "in_progress", "done"], default="open"
    )
    add_task_cmd.set_defaults(func=add_task)

    upd_task_cmd = sub.add_parser("update-task", help="Update task status")
    upd_task_cmd.add_argument("--project", required=True, help="Project identifier")
    upd_task_cmd.add_argument("--id", required=True, type=int, help="Task ID")
    upd_task_cmd.add_argument(
        "--status", required=True, choices=["open", "in_progress", "done"]
    )
    upd_task_cmd.set_defaults(func=update_task)

    recall_cmd = sub.add_parser(
        "recall", help="Recall shared memory context for startup prompt"
    )
    recall_cmd.add_argument("--project", required=True, help="Project identifier")
    recall_cmd.add_argument("--limit-events", type=int, default=12)
    recall_cmd.add_argument("--limit-tasks", type=int, default=10)
    recall_cmd.add_argument(
        "--pretty-context",
        action="store_true",
        help="Print concise prompt-ready text context",
    )
    recall_cmd.set_defaults(func=recall)

    auto_import_cmd = sub.add_parser(
        "auto-import-cursor",
        help="Auto ingest Cursor transcripts into shared memory",
    )
    auto_import_cmd.add_argument("--project", required=True, help="Project identifier")
    auto_import_cmd.add_argument(
        "--cursor-projects-dir",
        default=str(CURSOR_PROJECTS_DIR),
        help="Cursor projects directory to scan",
    )
    auto_import_cmd.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and import new entries continuously",
    )
    auto_import_cmd.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Watch polling interval in seconds (watch mode)",
    )
    auto_import_cmd.set_defaults(func=auto_import_cursor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        raise SystemExit(130)
