#!/usr/bin/env python3
"""
Risk Score Calculator for orchestration plans.

Usage:
    python3 ~/.claude/orchestrator_code/risk.py tasks.yaml
    python3 ~/.claude/orchestrator_code/risk.py --json tasks.yaml
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

SENSITIVE_PATTERNS = [
    (r"auth|security|crypto", 20),
    (r"payment|billing|stripe", 25),
    (r"prod|production|deploy", 30),
    (r"admin|sudo|root", 15),
    (r"\.env|secret|key|token", 25),
    (r"migration|schema|database", 15),
]


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


def compute_risk_score(plan: dict) -> dict:
    """Compute risk score for an execution plan."""
    score = 0
    factors = []
    tasks = plan.get("tasks", [])

    # Factor 1: Sensitive paths
    for task in tasks:
        for path in task.get("files_write", []):
            for pattern, weight in SENSITIVE_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    score += weight
                    factors.append(f"sensitive_path:{path}:{pattern.split('|')[0]}")
                    break

    # Factor 2: Scale - tasks
    num_tasks = len(tasks)
    if num_tasks > 5:
        score += (num_tasks - 5) * 5
        factors.append(f"many_tasks:{num_tasks}")

    # Factor 3: Scale - files
    num_files = sum(len(t.get("files_write", [])) for t in tasks)
    if num_files > 10:
        score += (num_files - 10) * 3
        factors.append(f"many_files:{num_files}")

    # Factor 4: Hot files (patch intents)
    hot_file_count = sum(len(t.get("patch_intents", [])) for t in tasks)
    if hot_file_count > 3:
        score += (hot_file_count - 3) * 5
        factors.append(f"many_hot_files:{hot_file_count}")

    # Factor 5: New dependencies
    new_deps = sum(
        len(t.get("deps_required", {}).get("runtime", []))
        for t in tasks
    )
    if new_deps > 0:
        score += new_deps * 3
        factors.append(f"new_dependencies:{new_deps}")

    # Factor 6: Contracts
    num_contracts = len(plan.get("contracts", []))
    if num_contracts > 3:
        score += (num_contracts - 3) * 5
        factors.append(f"many_contracts:{num_contracts}")

    # Factor 7: Test coverage
    tasks_with_tests = sum(
        1 for t in tasks
        if any(v.get("type") == "test" for v in t.get("verification", []))
    )
    if tasks and tasks_with_tests < len(tasks):
        coverage = tasks_with_tests / len(tasks)
        score += int((1.0 - coverage) * 20)
        factors.append(f"incomplete_test_coverage:{coverage:.0%}")

    auto_approve = score <= 25
    status = "AUTO-APPROVE" if auto_approve else ("REQUIRES REVIEW" if score <= 50 else "HIGH RISK")

    return {
        "score": score,
        "factors": factors,
        "auto_approve": auto_approve,
        "status": status
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compute risk score for orchestration plan")
    parser.add_argument("plan_file", help="Path to tasks.yaml or tasks.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    plan = load_plan(args.plan_file)
    result = compute_risk_score(plan)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nRisk Score: {result['score']} ({result['status']})")
        print("Factors:")
        for f in result['factors']:
            print(f"  - {f}")
        if result['auto_approve']:
            print("\n✓ Safe to auto-approve")
        else:
            print("\n⚠ Human review recommended")


if __name__ == "__main__":
    main()
