#!/usr/bin/env python3
"""
Risk Score Calculator for orchestration plans.

Usage:
    python3 ~/.claude/orchestrator_code/risk.py tasks.yaml
    python3 ~/.claude/orchestrator_code/risk.py --json tasks.yaml
    python3 ~/.claude/orchestrator_code/risk.py --config .claude-agents.yaml tasks.yaml

Sensitive patterns can be customized via .claude-agents.yaml:

    risk:
      sensitive_patterns:
        - pattern: "auth|security|crypto"
          weight: 20
        - pattern: "internal/proprietary/*"
          weight: 30
      auto_approve_threshold: 25
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# Default patterns used when no config is provided
DEFAULT_SENSITIVE_PATTERNS = [
    (r"auth|security|crypto", 20),
    (r"payment|billing|stripe", 25),
    (r"prod|production|deploy", 30),
    (r"admin|sudo|root", 15),
    (r"\.env|secret|key|token", 25),
    (r"migration|schema|database", 15),
]

# Default threshold for auto-approval
DEFAULT_AUTO_APPROVE_THRESHOLD = 25


def load_yaml_or_json(path: str) -> dict:
    """Load data from YAML or JSON file."""
    p = Path(path)
    content = p.read_text()

    if p.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def load_plan(path: str) -> dict:
    """Load plan from YAML or JSON file."""
    return load_yaml_or_json(path)


def load_config(config_path: str | None) -> dict:
    """Load risk configuration from .claude-agents.yaml or similar.

    Returns dict with:
        - sensitive_patterns: list of (pattern, weight) tuples
        - auto_approve_threshold: int
    """
    config = {
        "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
        "auto_approve_threshold": DEFAULT_AUTO_APPROVE_THRESHOLD,
    }

    # Try to find config file
    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    else:
        # Default search locations
        search_paths.extend([
            Path.cwd() / ".claude-agents.yaml",
            Path.cwd() / ".claude-agents.yml",
        ])

    config_file = None
    for p in search_paths:
        if p.exists():
            config_file = p
            break

    if config_file is None:
        return config

    try:
        data = load_yaml_or_json(str(config_file))
        risk_config = data.get("risk", {})

        # Load custom sensitive patterns
        if "sensitive_patterns" in risk_config:
            patterns = []
            for item in risk_config["sensitive_patterns"]:
                if isinstance(item, dict):
                    pattern = item.get("pattern", "")
                    weight = item.get("weight", 10)
                    patterns.append((pattern, weight))
                elif isinstance(item, str):
                    # Simple string pattern with default weight
                    patterns.append((item, 10))
            if patterns:
                config["sensitive_patterns"] = patterns

        # Load auto-approve threshold
        if "auto_approve_threshold" in risk_config:
            config["auto_approve_threshold"] = int(risk_config["auto_approve_threshold"])

    except Exception as e:
        print(f"Warning: Failed to load config from {config_file}: {e}", file=sys.stderr)

    return config


def compute_risk_score(plan: dict, config: dict | None = None) -> dict:
    """Compute risk score for an execution plan.

    Args:
        plan: The execution plan (tasks.yaml content)
        config: Optional config dict from load_config(). If None, uses defaults.
    """
    if config is None:
        config = {
            "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
            "auto_approve_threshold": DEFAULT_AUTO_APPROVE_THRESHOLD,
        }

    sensitive_patterns = config.get("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS)
    auto_approve_threshold = config.get("auto_approve_threshold", DEFAULT_AUTO_APPROVE_THRESHOLD)

    score = 0
    factors = []
    tasks = plan.get("tasks", [])

    # Pre-compile regex patterns for validation and performance
    compiled_patterns = []
    for pattern, weight in sensitive_patterns:
        try:
            compiled_patterns.append((re.compile(pattern, re.IGNORECASE), weight, pattern))
        except re.error as e:
            print(f"Warning: Invalid risk pattern '{pattern}': {e}", file=sys.stderr)

    # Factor 1: Sensitive paths
    for task in tasks:
        for path in task.get("files_write", []):
            for compiled, weight, raw_pattern in compiled_patterns:
                if compiled.search(path):
                    score += weight
                    factors.append(f"sensitive_path:{path}:{raw_pattern.split('|')[0]}")
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

    auto_approve = score <= auto_approve_threshold
    status = "AUTO-APPROVE" if auto_approve else ("REQUIRES REVIEW" if score <= auto_approve_threshold * 2 else "HIGH RISK")

    return {
        "score": score,
        "factors": factors,
        "auto_approve": auto_approve,
        "auto_approve_threshold": auto_approve_threshold,
        "status": status
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compute risk score for orchestration plan")
    parser.add_argument("plan_file", help="Path to tasks.yaml or tasks.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--config", help="Path to .claude-agents.yaml config file")
    args = parser.parse_args()

    config = load_config(args.config)
    plan = load_plan(args.plan_file)
    result = compute_risk_score(plan, config)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nRisk Score: {result['score']} ({result['status']})")
        print(f"Auto-approve threshold: {result['auto_approve_threshold']}")
        print("Factors:")
        for f in result['factors']:
            print(f"  - {f}")
        if result['auto_approve']:
            print("\n✓ Safe to auto-approve")
        else:
            print("\n⚠ Human review recommended")


if __name__ == "__main__":
    main()
