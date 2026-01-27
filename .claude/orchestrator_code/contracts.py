#!/usr/bin/env python3
"""
Interface Contract Generator for orchestration.

Generates Protocol stubs for cross-task dependencies.

Usage:
    python3 ~/.claude/orchestrator_code/contracts.py AuthServiceProtocol login logout verify
    python3 ~/.claude/orchestrator_code/contracts.py --output contracts/auth.py AuthServiceProtocol login logout
"""

import subprocess
import sys
from datetime import datetime


def get_git_version() -> str:
    """Get short commit hash for versioning."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def generate_contract(name: str, methods: list, version: str = None) -> str:
    """Generate a Protocol contract stub."""
    if version is None:
        version = get_git_version()

    timestamp = datetime.now().isoformat()

    lines = [
        '"""',
        f'Contract: {name}',
        f'Version: {version}',
        f'Generated: {timestamp}',
        '"""',
        'from typing import Protocol',
        '',
        '',
        f'class {name}(Protocol):',
    ]

    for method in methods:
        if isinstance(method, dict):
            mname = method.get("name", "method")
            params = method.get("params", "self")
            returns = method.get("returns", "None")
            doc = method.get("doc", "...")
        else:
            mname = method
            params = "self"
            returns = "None"
            doc = "..."

        lines.extend([
            f'    def {mname}({params}) -> {returns}:',
            f'        """{doc}"""',
            '        ...',
            '',
        ])

    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Protocol contract stub")
    parser.add_argument("name", help="Contract/Protocol name (e.g., AuthServiceProtocol)")
    parser.add_argument("methods", nargs="+", help="Method names")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--version", "-v", help="Version string (default: git commit hash)")
    args = parser.parse_args()

    contract = generate_contract(args.name, args.methods, args.version)

    if args.output:
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(contract)
        print(f"✓ Contract written to {args.output}")
    else:
        print(contract)


if __name__ == "__main__":
    main()
