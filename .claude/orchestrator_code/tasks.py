#!/usr/bin/env python3
"""
Task Status Utilities for orchestration.

Check task readiness and status.

Usage:
    python3 ~/.claude/orchestrator_code/tasks.py ready tasks.yaml
    python3 ~/.claude/orchestrator_code/tasks.py check-all
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def load_plan(path: str) -> dict:
    """Load plan from YAML or JSON file."""
    p = Path(path)
    content = p.read_text()

    if p.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def load_state() -> dict | None:
    """Load existing state or return None."""
    p = Path(".orchestration-state.json")
    if p.exists():
        return json.loads(p.read_text())
    return None


def get_task_status(task_id: str, state: dict = None) -> str:
    """Get current status of a task."""
    # Check worktree status file first
    status_file = Path(f".worktrees/{task_id}/.task-status.json")
    if status_file.exists():
        task_status = json.loads(status_file.read_text())
        return task_status.get("status", "pending")

    # Fall back to orchestration state
    if state:
        return state.get("tasks", {}).get(task_id, {}).get("status", "pending")

    return "pending"


def get_ready_tasks(tasks_file: str = "tasks.yaml") -> list:
    """Get tasks whose dependencies are all verified/merged."""
    plan = load_plan(tasks_file)
    state = load_state() or {"tasks": {}}

    ready = []
    for task in plan.get("tasks", []):
        task_id = task["id"]
        status = get_task_status(task_id, state)

        # Skip if already started or done
        if status != "pending":
            continue

        # Check dependencies
        deps = task.get("depends_on", [])
        deps_satisfied = all(
            get_task_status(dep, state) in ("verified", "merged")
            for dep in deps
        )

        if deps_satisfied:
            ready.append(task_id)

    return ready


def check_all_tasks() -> dict:
    """Check status of all tasks."""
    state = load_state()
    if state is None:
        return {"error": "No orchestration state found"}

    results = {
        "pending": [], "executing": [], "completed": [],
        "failed": [], "verified": [], "merged": []
    }

    for task_id in state.get("tasks", {}).keys():
        status = get_task_status(task_id, state)
        results.get(status, results["pending"]).append(task_id)

    total = len(state.get("tasks", {}))
    done = len(results["completed"]) + len(results["verified"]) + len(results["merged"])

    return {
        "results": results,
        "total": total,
        "done": done,
        "all_done": done == total,
        "any_failed": len(results["failed"]) > 0
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Task status utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ready command
    ready_parser = subparsers.add_parser("ready", help="Get tasks ready to execute")
    ready_parser.add_argument("tasks_file", nargs="?", default="tasks.yaml", help="Tasks file")
    ready_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # check-all command
    check_parser = subparsers.add_parser("check-all", help="Check all task statuses")
    check_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "ready":
        ready = get_ready_tasks(args.tasks_file)
        if args.json:
            print(json.dumps({"ready": ready}, indent=2))
        else:
            print(f"Ready to execute: {ready}")

    elif args.command == "check-all":
        result = check_all_tasks()
        if "error" in result:
            print(result["error"])
            sys.exit(1)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            r = result["results"]
            print("\nTask Status Summary:")
            print(f"  Pending:   {len(r['pending'])} - {r['pending']}")
            print(f"  Executing: {len(r['executing'])} - {r['executing']}")
            print(f"  Completed: {len(r['completed'])} - {r['completed']}")
            print(f"  Verified:  {len(r['verified'])} - {r['verified']}")
            print(f"  Merged:    {len(r['merged'])} - {r['merged']}")
            print(f"  Failed:    {len(r['failed'])} - {r['failed']}")

            if result["all_done"]:
                print("\n✓ All tasks completed")
            elif result["any_failed"]:
                print("\n✗ Some tasks failed")
            else:
                still_running = len(r["executing"])
                print(f"\n... {still_running} task(s) still running")


if __name__ == "__main__":
    main()
