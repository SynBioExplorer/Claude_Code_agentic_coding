#!/usr/bin/env python3
"""
Environment Hash Computation for orchestration.

Computes hash from lockfiles to ensure worker consistency.
Now hashes ALL present lockfiles (combined) to handle monorepos with multiple ecosystems.

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


def compute_env_hash(base_path: Path = None) -> tuple[str, list[str]]:
    """Compute environment hash from ALL present lockfiles.

    In monorepos with multiple ecosystems (Python + Node, etc.), we need to
    hash ALL lockfiles to ensure complete environment consistency.

    Returns:
        tuple of (combined_hash, list_of_lockfiles_found)
    """
    if base_path is None:
        base_path = Path.cwd()

    # Find ALL present lockfiles
    found_lockfiles = []
    for lockfile in LOCKFILES:
        path = base_path / lockfile
        if path.exists():
            found_lockfiles.append(lockfile)

    if not found_lockfiles:
        return "no-lock", []

    # Sort for deterministic ordering
    found_lockfiles.sort()

    # Compute combined hash of all lockfiles
    combined_hasher = hashlib.sha256()
    for lockfile in found_lockfiles:
        path = base_path / lockfile
        # Include filename in hash to distinguish between different lockfiles
        combined_hasher.update(lockfile.encode('utf-8'))
        combined_hasher.update(path.read_bytes())

    return combined_hasher.hexdigest()[:8], found_lockfiles


def compute_env_hash_legacy(base_path: Path = None) -> tuple[str, str | None]:
    """Legacy function: Compute hash from first found lockfile only.

    Kept for backwards compatibility. New code should use compute_env_hash().

    Returns (hash, lockfile_name) for first found lockfile.
    """
    if base_path is None:
        base_path = Path.cwd()

    for lockfile in LOCKFILES:
        path = base_path / lockfile
        if path.exists():
            content = path.read_bytes()
            return hashlib.sha256(content).hexdigest()[:8], lockfile

    return "no-lock", None


def verify_env_hash(expected: str, base_path: Path = None) -> tuple[bool, str, list[str]]:
    """Verify environment hash matches expected.

    Returns:
        tuple of (match, actual_hash, list_of_lockfiles)
    """
    actual, lockfiles = compute_env_hash(base_path)
    return actual == expected, actual, lockfiles


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compute or verify environment hash")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verify", help="Expected hash to verify against")
    parser.add_argument("--path", default=".", help="Base path to search for lockfiles")
    parser.add_argument("--legacy", action="store_true", help="Use legacy single-lockfile mode")
    args = parser.parse_args()

    base_path = Path(args.path)

    if args.verify:
        match, actual, lockfiles = verify_env_hash(args.verify, base_path)
        if args.json:
            print(json.dumps({
                "match": match,
                "expected": args.verify,
                "actual": actual,
                "lockfiles": lockfiles
            }, indent=2))
        else:
            if match:
                print(f"✓ Environment hash matches: {actual}")
                if lockfiles:
                    print(f"  Lockfiles: {', '.join(lockfiles)}")
            else:
                print(f"✗ Environment hash mismatch!")
                print(f"  Expected: {args.verify}")
                print(f"  Actual:   {actual}")
                if lockfiles:
                    print(f"  Lockfiles: {', '.join(lockfiles)}")
        sys.exit(0 if match else 1)
    else:
        if args.legacy:
            env_hash, lockfile = compute_env_hash_legacy(base_path)
            if args.json:
                print(json.dumps({
                    "hash": env_hash,
                    "lockfile": lockfile
                }, indent=2))
            else:
                print(f"Environment hash: {env_hash}")
                if lockfile:
                    print(f"Source: {lockfile}")
        else:
            env_hash, lockfiles = compute_env_hash(base_path)
            if args.json:
                print(json.dumps({
                    "hash": env_hash,
                    "lockfiles": lockfiles
                }, indent=2))
            else:
                print(f"Environment hash: {env_hash}")
                if lockfiles:
                    print(f"Sources: {', '.join(lockfiles)}")


if __name__ == "__main__":
    main()
