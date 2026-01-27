#!/usr/bin/env python3
"""
Environment Hash Computation for orchestration.

Computes hash from lockfiles to ensure worker consistency.

Usage:
    python3 ~/.claude/orchestrator_code/environment.py
    python3 ~/.claude/orchestrator_code/environment.py --json
    python3 ~/.claude/orchestrator_code/environment.py --verify abc12345
"""

import hashlib
import json
import sys
from pathlib import Path

LOCKFILES = [
    "uv.lock",
    "poetry.lock",
    "requirements.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
]


def compute_env_hash(base_path: Path = None) -> tuple[str, str | None]:
    """Compute environment hash from lockfile. Returns (hash, lockfile_name)."""
    if base_path is None:
        base_path = Path.cwd()

    for lockfile in LOCKFILES:
        path = base_path / lockfile
        if path.exists():
            content = path.read_bytes()
            return hashlib.sha256(content).hexdigest()[:8], lockfile

    return "no-lock", None


def verify_env_hash(expected: str, base_path: Path = None) -> tuple[bool, str, str | None]:
    """Verify environment hash matches expected. Returns (match, actual_hash, lockfile)."""
    actual, lockfile = compute_env_hash(base_path)
    return actual == expected, actual, lockfile


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compute or verify environment hash")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verify", help="Expected hash to verify against")
    parser.add_argument("--path", default=".", help="Base path to search for lockfiles")
    args = parser.parse_args()

    base_path = Path(args.path)

    if args.verify:
        match, actual, lockfile = verify_env_hash(args.verify, base_path)
        if args.json:
            print(json.dumps({
                "match": match,
                "expected": args.verify,
                "actual": actual,
                "lockfile": lockfile
            }, indent=2))
        else:
            if match:
                print(f"✓ Environment hash matches: {actual}")
            else:
                print(f"✗ Environment hash mismatch!")
                print(f"  Expected: {args.verify}")
                print(f"  Actual:   {actual}")
        sys.exit(0 if match else 1)
    else:
        env_hash, lockfile = compute_env_hash(base_path)
        if args.json:
            print(json.dumps({
                "hash": env_hash,
                "lockfile": lockfile
            }, indent=2))
        else:
            print(f"Environment hash: {env_hash}")
            if lockfile:
                print(f"Source: {lockfile}")


if __name__ == "__main__":
    main()
