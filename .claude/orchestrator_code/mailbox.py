#!/usr/bin/env python3
"""
Inter-Worker Mailbox System for Multi-Agent Orchestration.

Provides push-based messaging between workers, enabling real-time
coordination when one worker's changes affect another.

Messages are stored as individual JSON files using atomic write-tmp-then-rename
to prevent partial reads. Read marking uses atomic rename (.json → .read.json).

Directory structure:
    .orchestrator/mailbox/
    ├── worker-task-a/           # Inbox for task-a
    │   ├── msg-<uuid>.json      # Unread message
    │   └── msg-<uuid>.read.json # Read message
    ├── worker-task-b/           # Inbox for task-b
    └── broadcast/               # Messages for all workers
        └── msg-<uuid>.json

Usage:
    # Initialize mailboxes for all tasks
    python3 ~/.claude/orchestrator_code/mailbox.py init --tasks task-a task-b task-c

    # Send a message to a specific worker
    python3 ~/.claude/orchestrator_code/mailbox.py send task-b "Changed login() return type" --from worker-task-a

    # Send a structured message (JSON body)
    python3 ~/.claude/orchestrator_code/mailbox.py send task-b --json '{"type":"api_change","file":"src/api.py"}' --from worker-task-a

    # Broadcast to all workers
    python3 ~/.claude/orchestrator_code/mailbox.py broadcast "Database uses UUID primary keys" --from supervisor

    # Check inbox (returns unread messages, marks them as read)
    python3 ~/.claude/orchestrator_code/mailbox.py check task-b

    # Peek at inbox (returns unread count without marking read)
    python3 ~/.claude/orchestrator_code/mailbox.py peek task-b
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


MAILBOX_DIR = ".orchestrator/mailbox"
BROADCAST_DIR = "broadcast"


def _get_mailbox_root(project_dir: Optional[str] = None) -> Path:
    """Get the root mailbox directory."""
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / MAILBOX_DIR


def _get_inbox(task_id: str, project_dir: Optional[str] = None) -> Path:
    """Get the inbox directory for a specific task."""
    return _get_mailbox_root(project_dir) / task_id


def _get_broadcast_dir(project_dir: Optional[str] = None) -> Path:
    """Get the broadcast directory."""
    return _get_mailbox_root(project_dir) / BROADCAST_DIR


def _write_message_file(inbox_dir: Path, message: dict) -> Path:
    """Write a message file atomically using write-tmp-then-rename.

    Same pattern as tmux.py create_signal_file.
    """
    msg_file = inbox_dir / f"msg-{message['id']}.json"
    tmp_file = msg_file.with_suffix(".json.tmp")

    try:
        inbox_dir.mkdir(parents=True, exist_ok=True)
        tmp_file.write_text(json.dumps(message, indent=2))
        tmp_file.rename(msg_file)
        return msg_file
    except Exception:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except Exception:
                pass
        raise


def _make_message(
    to_task: str,
    body: str,
    from_agent: str,
    msg_type: str = "info",
    structured: Optional[dict] = None,
) -> dict:
    """Create a message dict."""
    msg = {
        "id": str(uuid.uuid4())[:8],
        "from": from_agent,
        "to": to_task,
        "type": msg_type,
        "body": body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if structured:
        msg["data"] = structured
    return msg


def _get_unread_messages(inbox_dir: Path) -> list[dict]:
    """Get all unread messages from an inbox directory.

    Unread messages are .json files (not .read.json or .tmp).
    """
    if not inbox_dir.exists():
        return []

    messages = []
    for f in sorted(inbox_dir.glob("msg-*.json")):
        # Skip read messages and temp files
        if f.name.endswith(".read.json") or f.name.endswith(".tmp"):
            continue
        try:
            messages.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            # Log dropped messages to stderr for debugging
            print(f"Warning: Skipping corrupt message file {f.name}: {e}", file=__import__('sys').stderr)
            continue

    # Sort by timestamp
    messages.sort(key=lambda m: m.get("timestamp", ""))
    return messages


def _mark_as_read(inbox_dir: Path, msg_id: str) -> None:
    """Mark a message as read by renaming .json → .read.json (atomic)."""
    msg_file = inbox_dir / f"msg-{msg_id}.json"
    read_file = inbox_dir / f"msg-{msg_id}.read.json"
    try:
        msg_file.rename(read_file)
    except FileNotFoundError:
        pass  # Already read or deleted


# === Public API ===


def init_mailbox(task_ids: list[str], project_dir: Optional[str] = None) -> None:
    """Initialize mailbox directories for all tasks."""
    root = _get_mailbox_root(project_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Create inbox for each task
    for task_id in task_ids:
        inbox = root / task_id
        inbox.mkdir(exist_ok=True)

    # Create broadcast directory
    broadcast = root / BROADCAST_DIR
    broadcast.mkdir(exist_ok=True)

    print(f"Initialized mailbox for {len(task_ids)} tasks at {root}")


def send_message(
    to_task: str,
    body: str,
    from_agent: str,
    msg_type: str = "info",
    structured: Optional[dict] = None,
    project_dir: Optional[str] = None,
) -> str:
    """Send a message to a specific worker's inbox.

    Returns the message ID.
    """
    message = _make_message(to_task, body, from_agent, msg_type, structured)
    inbox = _get_inbox(to_task, project_dir)
    _write_message_file(inbox, message)
    print(f"Sent message {message['id']} to {to_task} from {from_agent}")
    return message["id"]


def broadcast_message(
    body: str,
    from_agent: str,
    msg_type: str = "info",
    project_dir: Optional[str] = None,
) -> list[str]:
    """Broadcast a message to all workers via the broadcast directory.

    Returns list of message IDs (one per broadcast message).
    """
    message = _make_message("broadcast", body, from_agent, msg_type)
    broadcast_dir = _get_broadcast_dir(project_dir)
    _write_message_file(broadcast_dir, message)
    print(f"Broadcast message {message['id']} from {from_agent}")
    return [message["id"]]


def _get_seen_broadcasts(task_id: str, project_dir: Optional[str] = None) -> set[str]:
    """Load the set of broadcast message IDs already seen by this worker."""
    seen_file = _get_mailbox_root(project_dir) / BROADCAST_DIR / f".seen-by-{task_id}"
    if not seen_file.exists():
        return set()
    try:
        return set(seen_file.read_text().strip().split("\n"))
    except (OSError, ValueError):
        return set()


def _mark_broadcasts_seen(task_id: str, msg_ids: list[str], project_dir: Optional[str] = None) -> None:
    """Record broadcast message IDs as seen by this worker."""
    seen_file = _get_mailbox_root(project_dir) / BROADCAST_DIR / f".seen-by-{task_id}"
    existing = _get_seen_broadcasts(task_id, project_dir)
    existing.update(msg_ids)
    try:
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = seen_file.with_suffix(".tmp")
        tmp_file.write_text("\n".join(sorted(existing)))
        tmp_file.rename(seen_file)
    except OSError:
        pass


def check_inbox(task_id: str, project_dir: Optional[str] = None) -> list[dict]:
    """Check inbox for unread messages. Returns messages and marks them as read.

    Checks both the task's personal inbox and the broadcast directory.
    Broadcast deduplication uses per-worker .seen-by-{task_id} files.
    """
    all_messages = []

    # Check personal inbox
    inbox = _get_inbox(task_id, project_dir)
    personal = _get_unread_messages(inbox)
    all_messages.extend(personal)

    # Check broadcast directory (with per-worker deduplication)
    broadcast_dir = _get_broadcast_dir(project_dir)
    broadcasts = _get_unread_messages(broadcast_dir)
    # Filter out broadcasts from self
    broadcasts = [m for m in broadcasts if m.get("from") != f"worker-{task_id}"]
    # Filter out already-seen broadcasts
    seen_ids = _get_seen_broadcasts(task_id, project_dir)
    new_broadcasts = [m for m in broadcasts if m.get("id") not in seen_ids]
    all_messages.extend(new_broadcasts)

    # Sort all by timestamp
    all_messages.sort(key=lambda m: m.get("timestamp", ""))

    # Mark personal messages as read
    for msg in personal:
        _mark_as_read(inbox, msg["id"])

    # Track which broadcasts this worker has now seen
    if new_broadcasts:
        _mark_broadcasts_seen(
            task_id, [m["id"] for m in new_broadcasts], project_dir
        )

    if all_messages:
        print(f"=== Inbox for {task_id}: {len(all_messages)} message(s) ===\n")
        for msg in all_messages:
            ts = msg.get("timestamp", "unknown")[:19]
            print(f"[{ts}] From: {msg['from']} | Type: {msg['type']}")
            print(f"  {msg['body']}")
            if msg.get("data"):
                print(f"  Data: {json.dumps(msg['data'])}")
            print()
    else:
        print(f"No unread messages for {task_id}")

    return all_messages


def peek_inbox(task_id: str, project_dir: Optional[str] = None) -> int:
    """Peek at inbox without marking messages as read. Returns unread count."""
    inbox = _get_inbox(task_id, project_dir)
    personal = _get_unread_messages(inbox)

    broadcast_dir = _get_broadcast_dir(project_dir)
    broadcasts = _get_unread_messages(broadcast_dir)
    broadcasts = [m for m in broadcasts if m.get("from") != f"worker-{task_id}"]
    # Exclude already-seen broadcasts
    seen_ids = _get_seen_broadcasts(task_id, project_dir)
    broadcasts = [m for m in broadcasts if m.get("id") not in seen_ids]

    count = len(personal) + len(broadcasts)
    print(count)
    return count


def cleanup_mailbox(project_dir: Optional[str] = None) -> dict:
    """Clean up all mailbox state: read messages, .seen-by files, broadcast dir.

    Call at end of orchestration to prevent stale data from affecting next run.
    """
    root = _get_mailbox_root(project_dir)
    removed = 0

    if not root.exists():
        return {"removed": 0}

    # Clean .read.json files from all inboxes
    for read_file in root.glob("*/msg-*.read.json"):
        try:
            read_file.unlink()
            removed += 1
        except OSError:
            pass

    # Clean .seen-by-* files from broadcast dir
    broadcast_dir = _get_broadcast_dir(project_dir)
    if broadcast_dir.exists():
        for seen_file in broadcast_dir.glob(".seen-by-*"):
            try:
                seen_file.unlink()
                removed += 1
            except OSError:
                pass

    print(f"Cleaned up {removed} mailbox files")
    return {"removed": removed}


# === CLI ===


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        # Parse --tasks flag
        if "--tasks" not in sys.argv:
            print("Usage: mailbox.py init --tasks task-a task-b task-c")
            sys.exit(1)
        tasks_idx = sys.argv.index("--tasks") + 1
        task_ids = sys.argv[tasks_idx:]
        if not task_ids:
            print("Error: --tasks requires at least one task ID")
            sys.exit(1)
        init_mailbox(task_ids)

    elif command == "send":
        if len(sys.argv) < 4:
            print('Usage: mailbox.py send <recipient-task-id> "<message>" --from <sender>')
            print("       mailbox.py send <recipient-task-id> --json '{...}' --from <sender>")
            sys.exit(1)

        recipient = sys.argv[2]

        # Parse --from (required)
        if "--from" not in sys.argv:
            print("Error: --from is required")
            sys.exit(1)
        from_idx = sys.argv.index("--from") + 1
        from_agent = sys.argv[from_idx]

        # Parse --type (optional)
        msg_type = "info"
        if "--type" in sys.argv:
            type_idx = sys.argv.index("--type") + 1
            msg_type = sys.argv[type_idx]

        # Check for --json mode
        if "--json" in sys.argv:
            json_idx = sys.argv.index("--json") + 1
            try:
                structured = json.loads(sys.argv[json_idx])
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON: {e}")
                sys.exit(1)
            body = structured.get("details", structured.get("body", json.dumps(structured)))
            send_message(recipient, body, from_agent, msg_type, structured)
        else:
            body = sys.argv[3]
            send_message(recipient, body, from_agent, msg_type)

    elif command == "broadcast":
        if len(sys.argv) < 3:
            print('Usage: mailbox.py broadcast "<message>" --from <sender>')
            sys.exit(1)

        body = sys.argv[2]

        if "--from" not in sys.argv:
            print("Error: --from is required")
            sys.exit(1)
        from_idx = sys.argv.index("--from") + 1
        from_agent = sys.argv[from_idx]

        msg_type = "info"
        if "--type" in sys.argv:
            type_idx = sys.argv.index("--type") + 1
            msg_type = sys.argv[type_idx]

        broadcast_message(body, from_agent, msg_type)

    elif command == "check":
        if len(sys.argv) < 3:
            print("Usage: mailbox.py check <task-id>")
            sys.exit(1)
        task_id = sys.argv[2]
        check_inbox(task_id)

    elif command == "peek":
        if len(sys.argv) < 3:
            print("Usage: mailbox.py peek <task-id>")
            sys.exit(1)
        task_id = sys.argv[2]
        peek_inbox(task_id)

    elif command == "cleanup":
        cleanup_mailbox()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
