"""Environment hash computation and verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_orchestrator.schemas.config import OrchestrationConfig


@dataclass
class EnvironmentResult:
    """Result of environment setup or verification."""

    valid: bool
    env_hash: str | None = None
    error: str | None = None
    ecosystem: str | None = None
    lockfile_path: str | None = None


def compute_env_hash(lockfile_path: str | Path) -> str | None:
    """Compute environment hash from a lockfile.

    Args:
        lockfile_path: Path to the lockfile

    Returns:
        8-character hash of the lockfile content, or None if file doesn't exist
    """
    path = Path(lockfile_path)

    if not path.exists():
        return None

    try:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:8]
    except Exception:
        return None


def detect_lockfile(project_root: Path, config: OrchestrationConfig | None = None) -> Path | None:
    """Detect the lockfile for a project.

    Args:
        project_root: Root directory of the project
        config: Configuration with ecosystem settings

    Returns:
        Path to lockfile if found, None otherwise
    """
    # Check configured ecosystems first
    if config:
        for eco_name, eco_config in config.dependencies.ecosystems.items():
            lockfile = project_root / eco_config.lockfile
            if lockfile.exists():
                return lockfile

    # Fall back to common lockfiles
    common_lockfiles = [
        "uv.lock",
        "poetry.lock",
        "requirements.lock",
        "Pipfile.lock",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "Cargo.lock",
        "go.sum",
        "Gemfile.lock",
        "composer.lock",
    ]

    for lockfile in common_lockfiles:
        path = project_root / lockfile
        if path.exists():
            return path

    return None


def setup_environment(
    project_root: Path,
    config: OrchestrationConfig | None = None,
) -> EnvironmentResult:
    """Set up environment and compute hash.

    This should be called at Stage 0.5, before any workers spawn.

    Args:
        project_root: Root directory of the project
        config: Configuration with ecosystem settings

    Returns:
        EnvironmentResult with hash and status
    """
    lockfile = detect_lockfile(project_root, config)

    if not lockfile:
        return EnvironmentResult(
            valid=False,
            error="No lockfile found. Cannot compute environment hash.",
        )

    env_hash = compute_env_hash(lockfile)

    if not env_hash:
        return EnvironmentResult(
            valid=False,
            error=f"Failed to compute hash for lockfile: {lockfile}",
            lockfile_path=str(lockfile),
        )

    # Detect ecosystem from lockfile name
    ecosystem = detect_ecosystem(lockfile)

    return EnvironmentResult(
        valid=True,
        env_hash=env_hash,
        ecosystem=ecosystem,
        lockfile_path=str(lockfile),
    )


def detect_ecosystem(lockfile: Path) -> str:
    """Detect ecosystem from lockfile name.

    Args:
        lockfile: Path to lockfile

    Returns:
        Ecosystem name (python, node, rust, go, ruby, etc.)
    """
    name = lockfile.name.lower()

    ecosystem_map = {
        "uv.lock": "python",
        "poetry.lock": "python",
        "requirements.lock": "python",
        "pipfile.lock": "python",
        "package-lock.json": "node",
        "pnpm-lock.yaml": "node",
        "yarn.lock": "node",
        "cargo.lock": "rust",
        "go.sum": "go",
        "gemfile.lock": "ruby",
        "composer.lock": "php",
        "packages.lock.json": "dotnet",
    }

    return ecosystem_map.get(name, "unknown")


def validate_environment(
    task_env_hash: str | None,
    global_env_hash: str,
) -> EnvironmentResult:
    """Validate that a task used the correct environment.

    Args:
        task_env_hash: Hash recorded by the task
        global_env_hash: Expected hash from Stage 0.5

    Returns:
        EnvironmentResult indicating validity
    """
    if task_env_hash is None:
        return EnvironmentResult(
            valid=False,
            error="Task did not record environment hash.",
        )

    if task_env_hash != global_env_hash:
        return EnvironmentResult(
            valid=False,
            error=f"Environment mismatch: task used {task_env_hash}, "
            f"expected {global_env_hash}. Worker may have stale dependencies.",
        )

    return EnvironmentResult(
        valid=True,
        env_hash=global_env_hash,
    )


def get_env_hash_for_worktree(worktree_path: Path) -> str | None:
    """Get environment hash for a specific worktree.

    Args:
        worktree_path: Path to the worktree

    Returns:
        Environment hash, or None if not determinable
    """
    lockfile = detect_lockfile(worktree_path)
    if lockfile:
        return compute_env_hash(lockfile)
    return None
