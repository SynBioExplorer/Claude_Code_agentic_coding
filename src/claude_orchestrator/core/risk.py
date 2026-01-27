"""Risk scoring for approval gates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_orchestrator.schemas.config import OrchestrationConfig
    from claude_orchestrator.schemas.tasks import ExecutionPlan, TaskSpec


@dataclass
class RiskScore:
    """Risk assessment for an execution plan."""

    value: int
    factors: list[str] = field(default_factory=list)
    auto_approve: bool = False
    recommendation: str = ""

    def __str__(self) -> str:
        status = "AUTO-APPROVE" if self.auto_approve else "REQUIRES REVIEW"
        return f"Risk Score: {self.value} [{status}]"


# Default sensitive patterns with weights
DEFAULT_SENSITIVE_PATTERNS: list[tuple[str, int]] = [
    (r"auth|security|crypto", 20),
    (r"payment|billing|stripe", 25),
    (r"prod|production|deploy", 30),
    (r"admin|sudo|root", 15),
    (r"\.env|secret|key|token", 25),
    (r"migration|schema|database", 15),
]


def compute_risk_score(
    plan: ExecutionPlan,
    config: OrchestrationConfig | None = None,
) -> RiskScore:
    """Compute risk score for an execution plan.

    The risk score determines whether the plan can be auto-approved
    or requires human review.

    Args:
        plan: The execution plan to assess
        config: Configuration with thresholds and patterns

    Returns:
        RiskScore with value, factors, and auto_approve decision
    """
    score = 0
    factors: list[str] = []

    # Get configuration values
    if config:
        threshold = config.approval.auto_approve_threshold
        sensitive_patterns = [
            (p.pattern, p.weight) for p in config.approval.sensitive_patterns
        ]
    else:
        threshold = 25
        sensitive_patterns = DEFAULT_SENSITIVE_PATTERNS

    # Factor 1: Sensitive paths
    score, factors = _score_sensitive_paths(plan.tasks, sensitive_patterns, score, factors)

    # Factor 2: Scale (number of tasks and files)
    score, factors = _score_scale(plan.tasks, score, factors)

    # Factor 3: Hot files (patch intents)
    score, factors = _score_hot_files(plan.tasks, score, factors)

    # Factor 4: Dependency changes
    score, factors = _score_dependency_changes(plan.tasks, score, factors)

    # Factor 5: Contract complexity
    score, factors = _score_contracts(plan, score, factors)

    # Factor 6: Test coverage
    score, factors = _score_test_coverage(plan.tasks, score, factors)

    # Determine auto-approval
    auto_approve = score < threshold

    # Generate recommendation
    if score <= 25:
        recommendation = "Low risk - suitable for auto-approval"
    elif score <= 50:
        recommendation = "Moderate risk - human review recommended"
    else:
        recommendation = "High risk - human review required"

    return RiskScore(
        value=score,
        factors=factors,
        auto_approve=auto_approve,
        recommendation=recommendation,
    )


def _score_sensitive_paths(
    tasks: list[TaskSpec],
    patterns: list[tuple[str, int]],
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on sensitive file paths."""
    for task in tasks:
        for path in task.files_write:
            for pattern, weight in patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    score += weight
                    factors.append(f"sensitive_path:{path}:{pattern}")
    return score, factors


def _score_scale(
    tasks: list[TaskSpec],
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on plan scale (tasks and files)."""
    num_tasks = len(tasks)
    num_files = sum(len(t.files_write) for t in tasks)

    if num_tasks > 5:
        added = (num_tasks - 5) * 5
        score += added
        factors.append(f"many_tasks:{num_tasks}")

    if num_files > 10:
        added = (num_files - 10) * 3
        score += added
        factors.append(f"many_files:{num_files}")

    return score, factors


def _score_hot_files(
    tasks: list[TaskSpec],
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on patch intents (hot file modifications)."""
    hot_file_count = sum(len(t.patch_intents) for t in tasks)

    if hot_file_count > 3:
        added = (hot_file_count - 3) * 5
        score += added
        factors.append(f"many_hot_files:{hot_file_count}")

    return score, factors


def _score_dependency_changes(
    tasks: list[TaskSpec],
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on new package dependencies."""
    new_deps = 0

    for task in tasks:
        if task.deps_required:
            new_deps += len(task.deps_required.runtime)

    if new_deps > 0:
        added = new_deps * 3
        score += added
        factors.append(f"new_dependencies:{new_deps}")

    return score, factors


def _score_contracts(
    plan: ExecutionPlan,
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on interface contract complexity."""
    if len(plan.contracts) > 3:
        added = (len(plan.contracts) - 3) * 5
        score += added
        factors.append(f"many_contracts:{len(plan.contracts)}")

    return score, factors


def _score_test_coverage(
    tasks: list[TaskSpec],
    score: int,
    factors: list[str],
) -> tuple[int, list[str]]:
    """Score based on test verification coverage."""
    tasks_with_tests = sum(
        1
        for t in tasks
        if any(v.type.value == "test" for v in t.verification)
    )

    if not tasks:
        return score, factors

    test_coverage_ratio = tasks_with_tests / len(tasks)

    if test_coverage_ratio < 1.0:
        added = int((1.0 - test_coverage_ratio) * 20)
        score += added
        factors.append(f"incomplete_test_coverage:{test_coverage_ratio:.0%}")

    return score, factors


def get_risk_summary(risk: RiskScore, threshold: int = 25) -> str:
    """Generate a human-readable risk summary.

    Args:
        risk: The computed risk score
        threshold: The auto-approval threshold

    Returns:
        Formatted summary string
    """
    lines = [
        f"Risk Score: {risk.value} (threshold: {threshold})",
        f"Status: {'AUTO-APPROVE' if risk.auto_approve else 'REQUIRES REVIEW'}",
        f"Recommendation: {risk.recommendation}",
    ]

    if risk.factors:
        lines.append("\nRisk Factors:")
        for factor in risk.factors:
            lines.append(f"  - {factor}")

    return "\n".join(lines)
