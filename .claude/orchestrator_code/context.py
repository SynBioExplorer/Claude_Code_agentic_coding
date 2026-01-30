#!/usr/bin/env python3
"""
Shared Context System for Multi-Agent Orchestration.

Provides a persistent knowledge store that all agents can read/write to.
Context is stored in .context/ directory as JSON files.

Usage:
    # Initialize context for a project
    python3 context.py init

    # Add a context entry
    python3 context.py add "architecture" "Using FastAPI with SQLAlchemy"

    # Add structured context
    python3 context.py add "database.schema" '{"users": ["id", "email", "password_hash"]}'

    # Read a context entry
    python3 context.py get "architecture"

    # List all context
    python3 context.py list

    # Search context
    python3 context.py search "database"

    # Delete a context entry
    python3 context.py delete "old_decision"
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import re

CONTEXT_DIR = ".context"
CONTEXT_FILE = ".context/knowledge.json"


def get_context_path(project_dir: Optional[str] = None) -> Path:
    """Get the path to the context file."""
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / CONTEXT_FILE


def get_context_dir(project_dir: Optional[str] = None) -> Path:
    """Get the path to the context directory."""
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / CONTEXT_DIR


def init_context(project_dir: Optional[str] = None) -> dict:
    """Initialize the context directory and file."""
    context_dir = get_context_dir(project_dir)
    context_path = get_context_path(project_dir)

    context_dir.mkdir(exist_ok=True)

    if context_path.exists():
        print(f"Context already exists at {context_path}")
        return load_context(project_dir)

    initial_context = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "entries": {}
    }

    with open(context_path, 'w') as f:
        json.dump(initial_context, f, indent=2)

    print(f"Initialized context at {context_path}")
    return initial_context


def load_context(project_dir: Optional[str] = None) -> dict:
    """Load the context from disk."""
    context_path = get_context_path(project_dir)

    if not context_path.exists():
        return init_context(project_dir)

    with open(context_path, 'r') as f:
        return json.load(f)


def save_context(context: dict, project_dir: Optional[str] = None) -> None:
    """Save the context to disk atomically.

    Uses temp file + fsync + rename for atomic writes.
    """
    import tempfile
    import os

    context_path = get_context_path(project_dir)
    context["updated_at"] = datetime.now().isoformat()

    # Atomic write: temp file + fsync + rename
    dir_path = context_path.parent
    fd = None
    temp_path = None

    try:
        fd, temp_path = tempfile.mkstemp(
            suffix='.tmp',
            prefix='context_',
            dir=str(dir_path)
        )
        content = json.dumps(context, indent=2)
        os.write(fd, content.encode('utf-8'))
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.rename(temp_path, context_path)
        temp_path = None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def load_and_lock_context(project_dir: Optional[str] = None) -> tuple[dict, Any]:
    """Load context with exclusive lock held for read-modify-write operations.

    IMPORTANT: The returned lock file handle MUST be closed by calling
    release_context_lock() after modifications are saved.

    This prevents lost updates where:
    - Agent A: load → modify
    - Agent B: load → modify → save (overwrites)
    - Agent A: save (A's changes lost, B's changes lost)

    Returns:
        tuple of (context_dict, lock_file_handle)
    """
    import fcntl

    context_path = get_context_path(project_dir)
    lock_path = context_path.with_suffix('.lock')

    # Ensure lock file exists
    lock_path.touch()

    # Open and acquire exclusive lock
    lock_file = open(lock_path, 'r+')
    fcntl.flock(lock_file, fcntl.LOCK_EX)

    # Now load the context while holding the lock
    if context_path.exists():
        with open(context_path, 'r') as f:
            context = json.load(f)
    else:
        context = init_context(project_dir)

    return context, lock_file


def save_and_release_context(
    context: dict,
    lock_file: Any,
    project_dir: Optional[str] = None
) -> None:
    """Save context and release the lock.

    Must be called after load_and_lock_context() to complete the
    read-modify-write cycle.

    Args:
        context: Modified context dict to save
        lock_file: Lock file handle from load_and_lock_context()
        project_dir: Optional project directory
    """
    import fcntl

    try:
        # Save the context atomically
        save_context(context, project_dir)
    finally:
        # Always release the lock
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def release_context_lock(lock_file: Any) -> None:
    """Release a context lock without saving (e.g., on error).

    Args:
        lock_file: Lock file handle from load_and_lock_context()
    """
    import fcntl
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass


def add_entry(key: str, value: Any, agent: str = "unknown", project_dir: Optional[str] = None) -> None:
    """Add or update a context entry with proper locking.

    Uses load_and_lock_context to prevent lost updates from concurrent modifications.
    """
    # Load with lock to prevent lost updates
    context, lock_file = load_and_lock_context(project_dir)

    try:
        # Try to parse value as JSON if it's a string
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string

        context["entries"][key] = {
            "value": value,
            "added_by": agent,
            "added_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        # Save and release lock
        save_and_release_context(context, lock_file, project_dir)
        print(f"Added context: {key}")

    except Exception as e:
        # Release lock on error
        release_context_lock(lock_file)
        raise e


def get_entry(key: str, project_dir: Optional[str] = None) -> Optional[Any]:
    """Get a context entry by key."""
    context = load_context(project_dir)

    if key in context["entries"]:
        entry = context["entries"][key]
        return entry["value"]

    # Support dot notation for nested access
    if "." in key:
        parts = key.split(".")
        current = context["entries"]
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                if isinstance(current, dict) and "value" in current:
                    current = current["value"]
            else:
                return None
        return current

    return None


def list_entries(project_dir: Optional[str] = None) -> dict:
    """List all context entries."""
    context = load_context(project_dir)
    return context["entries"]


def search_entries(query: str, project_dir: Optional[str] = None) -> dict:
    """Search context entries by key or value."""
    context = load_context(project_dir)
    results = {}

    query_lower = query.lower()

    for key, entry in context["entries"].items():
        # Search in key
        if query_lower in key.lower():
            results[key] = entry
            continue

        # Search in value
        value_str = json.dumps(entry["value"]) if not isinstance(entry["value"], str) else entry["value"]
        if query_lower in value_str.lower():
            results[key] = entry

    return results


def delete_entry(key: str, project_dir: Optional[str] = None) -> bool:
    """Delete a context entry with proper locking.

    Uses load_and_lock_context to prevent lost updates from concurrent modifications.
    """
    context, lock_file = load_and_lock_context(project_dir)

    try:
        if key in context["entries"]:
            del context["entries"][key]
            save_and_release_context(context, lock_file, project_dir)
            print(f"Deleted context: {key}")
            return True

        # Key not found, just release lock
        release_context_lock(lock_file)
        print(f"Context not found: {key}")
        return False

    except Exception as e:
        release_context_lock(lock_file)
        raise e


def format_entries(entries: dict) -> str:
    """Format entries for display."""
    if not entries:
        return "No entries found."

    lines = []
    for key, entry in entries.items():
        value = entry["value"]
        if isinstance(value, dict) or isinstance(value, list):
            value_str = json.dumps(value, indent=2)
            lines.append(f"\n{key}:")
            for line in value_str.split("\n"):
                lines.append(f"  {line}")
        else:
            lines.append(f"{key}: {value}")
        lines.append(f"  (by {entry.get('added_by', 'unknown')} at {entry.get('added_at', 'unknown')[:10]})")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        init_context()

    elif command == "add":
        if len(sys.argv) < 4:
            print("Usage: context.py add <key> <value> [--agent <agent_name>]")
            sys.exit(1)
        key = sys.argv[2]
        value = sys.argv[3]
        agent = "cli"
        if "--agent" in sys.argv:
            agent_idx = sys.argv.index("--agent") + 1
            if agent_idx < len(sys.argv):
                agent = sys.argv[agent_idx]
        add_entry(key, value, agent)

    elif command == "get":
        if len(sys.argv) < 3:
            print("Usage: context.py get <key>")
            sys.exit(1)
        key = sys.argv[2]
        value = get_entry(key)
        if value is not None:
            if isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2))
            else:
                print(value)
        else:
            print(f"Not found: {key}")
            sys.exit(1)

    elif command == "list":
        entries = list_entries()
        print(format_entries(entries))

    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: context.py search <query>")
            sys.exit(1)
        query = sys.argv[2]
        results = search_entries(query)
        print(format_entries(results))

    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: context.py delete <key>")
            sys.exit(1)
        key = sys.argv[2]
        delete_entry(key)

    elif command == "--json":
        # Output full context as JSON
        context = load_context()
        print(json.dumps(context, indent=2))

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
