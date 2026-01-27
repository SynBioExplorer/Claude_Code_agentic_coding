#!/usr/bin/env python3
"""
Conflict Detection for orchestration plans.

Detects file and resource conflicts between tasks.

Usage:
    python3 ~/.claude/orchestrator_code/conflict.py tasks.yaml
    python3 ~/.claude/orchestrator_code/conflict.py --json tasks.yaml
"""

import json
import sys
from collections import defaultdict
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


def get_implied_resources(intent: dict) -> list:
    """Extract implied resources from patch intents."""
    action = intent.get("action", "")
    data = intent.get("intent", {})

    if action == "add_router":
        return [f"route:{data.get('prefix', '/')}"]
    elif action == "add_dependency":
        return [f"di:{data.get('function_name', '')}"]
    elif action == "add_config":
        return [f"config:{data.get('key', '')}"]
    elif action == "add_middleware":
        return [f"middleware:{data.get('middleware_class', '')}"]
    return []


def detect_conflicts(tasks: list) -> list:
    """Detect file and resource conflicts between tasks."""
    conflicts = []
    file_writes = defaultdict(list)
    resource_writes = defaultdict(list)

    # Build dependency map
    task_deps = {t["id"]: set(t.get("depends_on", [])) for t in tasks}

    def has_dependency_path(from_task, to_task, visited=None):
        if visited is None:
            visited = set()
        if from_task in visited:
            return False
        visited.add(from_task)
        if to_task in task_deps.get(from_task, set()):
            return True
        for dep in task_deps.get(from_task, set()):
            if has_dependency_path(dep, to_task, visited):
                return True
        return False

    def tasks_ordered(task_ids):
        """Check if tasks have explicit ordering via dependencies."""
        for i, t1 in enumerate(task_ids):
            for t2 in task_ids[i+1:]:
                if has_dependency_path(t1, t2) or has_dependency_path(t2, t1):
                    return True
        return False

    # Collect writes
    for task in tasks:
        tid = task["id"]
        for f in task.get("files_write", []):
            file_writes[f].append(tid)
        for r in task.get("resources_write", []):
            resource_writes[r].append(tid)
        for intent in task.get("patch_intents", []):
            for r in get_implied_resources(intent):
                resource_writes[r].append(tid)

    # Check file conflicts
    for file, writers in file_writes.items():
        if len(writers) > 1 and not tasks_ordered(writers):
            conflicts.append({"type": "file", "target": file, "tasks": writers})

    # Check resource conflicts
    for resource, writers in resource_writes.items():
        if len(writers) > 1 and not tasks_ordered(writers):
            conflicts.append({"type": "resource", "target": resource, "tasks": writers})

    return conflicts


def suggest_fix(conflict: dict) -> str:
    """Suggest dependency to resolve conflict."""
    tasks = conflict["tasks"]
    return f"Add dependency: {tasks[1]} depends_on [{tasks[0]}]"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Detect conflicts in orchestration plan")
    parser.add_argument("plan_file", help="Path to tasks.yaml or tasks.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    plan = load_plan(args.plan_file)
    conflicts = detect_conflicts(plan.get("tasks", []))

    if args.json:
        print(json.dumps({"conflicts": conflicts, "count": len(conflicts)}, indent=2))
        sys.exit(1 if conflicts else 0)

    if conflicts:
        print(f"\n⚠ Found {len(conflicts)} conflict(s):\n")
        for c in conflicts:
            print(f"  [{c['type'].upper()}] {c['target']}")
            print(f"    Tasks: {', '.join(c['tasks'])}")
            print(f"    Fix: {suggest_fix(c)}\n")
        sys.exit(1)
    else:
        print("\n✓ No conflicts detected")


if __name__ == "__main__":
    main()
