"""File boundary validation for verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from claude_orchestrator.core.environment import validate_environment
from claude_orchestrator.schemas.status import BoundaryViolation, VerificationResult
from claude_orchestrator.worktree.isolation import validate_boundaries as isolation_validate

if TYPE_CHECKING:
    from claude_orchestrator.schemas.config import OrchestrationConfig
    from claude_orchestrator.schemas.status import OrchestrationState, TaskStatus
    from claude_orchestrator.schemas.tasks import TaskSpec


@dataclass
class FullVerificationResult:
    """Complete verification result including all checks."""

    task_id: str
    verification_passed: bool
    boundaries_valid: bool
    contracts_valid: bool
    environment_valid: bool
    checks: list[dict] = field(default_factory=list)
    boundary_violations: list[BoundaryViolation] = field(default_factory=list)
    contract_errors: list[str] = field(default_factory=list)
    environment_error: str | None = None
    verified_at: str = ""

    def __post_init__(self) -> None:
        if not self.verified_at:
            self.verified_at = datetime.now().isoformat()

    @property
    def all_valid(self) -> bool:
        """Check if all validations passed."""
        return (
            self.verification_passed
            and self.boundaries_valid
            and self.contracts_valid
            and self.environment_valid
        )


def validate_task_fully(
    task_id: str,
    task_spec: TaskSpec,
    task_status: TaskStatus,
    global_state: OrchestrationState,
    config: OrchestrationConfig,
    worktree_base: Path,
) -> FullVerificationResult:
    """Perform full verification of a task.

    Includes:
    1. Verification command results (from task_status)
    2. File boundary validation
    3. Contract version checking
    4. Environment hash verification

    Args:
        task_id: Task identifier
        task_spec: Task specification
        task_status: Current task status with verification results
        global_state: Global orchestration state
        config: Configuration
        worktree_base: Base path for worktrees

    Returns:
        FullVerificationResult with all check results
    """
    # 1. Get verification command results
    verification_passed = True
    checks: list[dict] = []

    if task_status.verification_result:
        verification_passed = task_status.verification_result.verification_passed
        checks = [
            {
                "command": c.command,
                "resolved_command": c.resolved_command,
                "type": c.type,
                "required": c.required,
                "passed": c.passed,
                "output": c.output,
                "error": c.error,
                "duration_ms": c.duration_ms,
            }
            for c in task_status.verification_result.checks
        ]

    # 2. Validate file boundaries
    boundary_result = isolation_validate(
        task_id=task_id,
        task_spec=task_spec,
        config=config,
        worktree_base=worktree_base,
    )

    # 3. Validate contract versions
    contracts_valid, contract_errors = validate_contracts(
        task_status=task_status,
        global_state=global_state,
        config=config,
    )

    # 4. Validate environment hash
    environment_valid = True
    environment_error = None

    if config.dependencies.verify_env_hash and global_state.environment:
        task_env_hash = (
            task_status.environment.hash if task_status.environment else None
        )
        env_result = validate_environment(
            task_env_hash=task_env_hash,
            global_env_hash=global_state.environment.hash,
        )
        environment_valid = env_result.valid
        environment_error = env_result.error

    return FullVerificationResult(
        task_id=task_id,
        verification_passed=verification_passed,
        boundaries_valid=boundary_result.valid,
        contracts_valid=contracts_valid,
        environment_valid=environment_valid,
        checks=checks,
        boundary_violations=boundary_result.violations,
        contract_errors=contract_errors,
        environment_error=environment_error,
    )


def validate_contracts(
    task_status: TaskStatus,
    global_state: OrchestrationState,
    config: OrchestrationConfig,
) -> tuple[bool, list[str]]:
    """Validate contract versions used by a task.

    Args:
        task_status: Task status with contracts_used
        global_state: Global state with contract definitions
        config: Configuration

    Returns:
        Tuple of (valid, list of error messages)
    """
    if not config.contracts.version_enforcement:
        return True, []

    errors: list[str] = []

    # For each contract the task claims to have used,
    # verify it matches the expected version
    for contract_name, usage in task_status.contracts_used.items():
        # In a full implementation, we'd check against the contracts
        # defined in the execution plan. For now, we just validate
        # the contract was properly recorded.
        if not usage.version:
            errors.append(f"Contract {contract_name} has no version recorded")

    return len(errors) == 0, errors


def get_boundary_summary(violations: list[BoundaryViolation]) -> str:
    """Generate a summary of boundary violations.

    Args:
        violations: List of violations

    Returns:
        Human-readable summary
    """
    if not violations:
        return "No boundary violations."

    lines = [f"Found {len(violations)} boundary violation(s):"]

    # Group by type
    by_type: dict[str, list[BoundaryViolation]] = {}
    for v in violations:
        by_type.setdefault(v.type, []).append(v)

    for vtype, vlist in by_type.items():
        lines.append(f"\n{vtype.replace('_', ' ').title()} ({len(vlist)}):")
        for v in vlist:
            lines.append(f"  - {v.file}: {v.message}")

    return "\n".join(lines)
