#!/usr/bin/env python3
"""
DAG Validation and Topological Sort for orchestration plans.

Detects cycles and computes execution waves.

Usage:
    python3 ~/.claude/orchestrator_code/dag.py tasks.yaml
    python3 ~/.claude/orchestrator_code/dag.py --json tasks.yaml
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
    """Load plan from YAML or JSON file.

    NOTE: Canonical implementation is in state.py. Kept here for standalone CLI use.
    """
    p = Path(path)
    content = p.read_text()

    if p.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def validate_dependency_ids(tasks: list) -> list[str]:
    """Validate that all dependency IDs reference existing tasks.

    Returns list of error messages (empty if valid).
    """
    task_ids = {t["id"] for t in tasks}
    errors = []
    for task in tasks:
        for dep in task.get("depends_on", []):
            if dep not in task_ids:
                errors.append(
                    f"Task '{task['id']}' depends on '{dep}' which does not exist. "
                    f"Known task IDs: {sorted(task_ids)}"
                )
    return errors


def detect_cycles(tasks: list) -> list | None:
    """Detect circular dependencies in task DAG. Returns cycle path or None."""
    graph = defaultdict(list)
    for task in tasks:
        tid = task["id"]
        for dep in task.get("depends_on", []):
            graph[dep].append(tid)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def dfs(node, path):
        color[node] = GRAY
        path.append(node)
        for neighbor in graph[node]:
            if color.get(neighbor, WHITE) == GRAY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if color.get(neighbor, WHITE) == WHITE:
                result = dfs(neighbor, path)
                if result:
                    return result
        path.pop()
        color[node] = BLACK
        return None

    for task in tasks:
        if color[task["id"]] == WHITE:
            cycle = dfs(task["id"], [])
            if cycle:
                return cycle
    return None


def topological_sort(tasks: list) -> list | None:
    """Return tasks in execution order (parallel waves). None if cycle detected."""
    in_degree = {t["id"]: len(t.get("depends_on", [])) for t in tasks}
    waves = []
    remaining = set(t["id"] for t in tasks)

    while remaining:
        wave = [tid for tid in remaining if in_degree[tid] == 0]
        if not wave:
            return None  # Cycle detected
        waves.append(wave)
        for tid in wave:
            remaining.remove(tid)
            for t in tasks:
                if tid in t.get("depends_on", []):
                    in_degree[t["id"]] -= 1

    return waves


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate DAG and compute execution waves")
    parser.add_argument("plan_file", help="Path to tasks.yaml or tasks.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    plan = load_plan(args.plan_file)
    tasks = plan.get("tasks", [])

    # Validate dependency IDs exist before cycle detection
    dep_errors = validate_dependency_ids(tasks)
    if dep_errors:
        if args.json:
            print(json.dumps({"valid": False, "errors": dep_errors}, indent=2))
        else:
            print(f"\n✗ Invalid dependency references:")
            for err in dep_errors:
                print(f"  - {err}")
        sys.exit(1)

    cycle = detect_cycles(tasks)

    if cycle:
        if args.json:
            print(json.dumps({"valid": False, "cycle": cycle}, indent=2))
        else:
            print(f"\n✗ Circular dependency detected: {' → '.join(cycle)}")
        sys.exit(1)

    waves = topological_sort(tasks)

    if args.json:
        print(json.dumps({
            "valid": True,
            "waves": waves,
            "total_waves": len(waves),
            "total_tasks": len(tasks)
        }, indent=2))
    else:
        print("\n✓ DAG is valid")
        print(f"\nExecution waves ({len(waves)} waves):")
        for i, wave in enumerate(waves):
            print(f"  Wave {i+1}: {', '.join(wave)}")


if __name__ == "__main__":
    main()
