"""Tests for risk scoring."""

import pytest

from claude_orchestrator.core.risk import (
    RiskScore,
    compute_risk_score,
    get_risk_summary,
)
from claude_orchestrator.schemas.config import OrchestrationConfig
from claude_orchestrator.schemas.tasks import (
    ContractSpec,
    DependencySpec,
    ExecutionPlan,
    TaskSpec,
    VerificationCheck,
    VerificationType,
)


def make_task(
    task_id: str,
    files_write: list[str] | None = None,
    verification_type: VerificationType = VerificationType.TEST,
    deps_required: DependencySpec | None = None,
    patch_intents_count: int = 0,
) -> TaskSpec:
    """Helper to create a TaskSpec for testing."""
    return TaskSpec(
        id=task_id,
        description=f"Test task {task_id}",
        files_write=files_write or [f"src/{task_id}.py"],
        depends_on=[],
        verification=[
            VerificationCheck(
                command=f"pytest tests/test_{task_id}.py",
                type=verification_type,
                required=True,
            )
        ],
        deps_required=deps_required,
        patch_intents=[
            {"file": f"main{i}.py", "action": "add_router", "intent": {"prefix": f"/api{i}"}}
            for i in range(patch_intents_count)
        ],
    )


def make_plan(
    tasks: list[TaskSpec],
    contracts: list[ContractSpec] | None = None,
) -> ExecutionPlan:
    """Helper to create an ExecutionPlan for testing."""
    return ExecutionPlan(
        request="Test request",
        tasks=tasks,
        contracts=contracts or [],
        created_at="2025-01-27T10:00:00Z",
    )


class TestComputeRiskScore:
    """Tests for compute_risk_score."""

    def test_minimal_plan_low_risk(self) -> None:
        """Test minimal plan has low risk."""
        plan = make_plan([make_task("a")])
        risk = compute_risk_score(plan)

        assert risk.value < 25
        assert risk.auto_approve is True

    def test_sensitive_path_increases_risk(self) -> None:
        """Test sensitive paths increase risk score."""
        plan = make_plan([
            make_task("a", files_write=["src/auth/login.py"]),
        ])
        risk = compute_risk_score(plan)

        assert risk.value > 0
        assert any("sensitive_path" in f for f in risk.factors)

    def test_payment_path_high_weight(self) -> None:
        """Test payment paths have high weight."""
        plan = make_plan([
            make_task("a", files_write=["src/payment/stripe.py"]),
        ])
        risk = compute_risk_score(plan)

        assert risk.value >= 25  # Payment pattern weight is 25

    def test_many_tasks_increases_risk(self) -> None:
        """Test many tasks increase risk."""
        tasks = [make_task(f"task-{i}") for i in range(10)]
        plan = make_plan(tasks)
        risk = compute_risk_score(plan)

        assert any("many_tasks" in f for f in risk.factors)

    def test_many_files_increases_risk(self) -> None:
        """Test many files increase risk."""
        plan = make_plan([
            make_task("a", files_write=[f"src/file{i}.py" for i in range(15)]),
        ])
        risk = compute_risk_score(plan)

        assert any("many_files" in f for f in risk.factors)

    def test_many_hot_files_increases_risk(self) -> None:
        """Test many patch intents increase risk."""
        plan = make_plan([
            make_task("a", patch_intents_count=5),
        ])
        risk = compute_risk_score(plan)

        assert any("many_hot_files" in f for f in risk.factors)

    def test_new_dependencies_increase_risk(self) -> None:
        """Test new dependencies increase risk."""
        plan = make_plan([
            make_task(
                "a",
                deps_required=DependencySpec(
                    runtime=["package1", "package2", "package3"],
                ),
            ),
        ])
        risk = compute_risk_score(plan)

        assert any("new_dependencies" in f for f in risk.factors)

    def test_many_contracts_increases_risk(self) -> None:
        """Test many contracts increase risk."""
        contracts = [
            ContractSpec(
                name=f"Protocol{i}",
                version="abc123",
                file_path=f"contracts/protocol{i}.py",
                created_at="2025-01-27T10:00:00Z",
            )
            for i in range(5)
        ]
        plan = make_plan([make_task("a")], contracts=contracts)
        risk = compute_risk_score(plan)

        assert any("many_contracts" in f for f in risk.factors)

    def test_incomplete_test_coverage_increases_risk(self) -> None:
        """Test incomplete test coverage increases risk."""
        plan = make_plan([
            make_task("a", verification_type=VerificationType.TEST),
            make_task("b", verification_type=VerificationType.LINT),  # No test
        ])
        risk = compute_risk_score(plan)

        assert any("test_coverage" in f for f in risk.factors)

    def test_auto_approve_below_threshold(self) -> None:
        """Test auto-approve when below threshold."""
        plan = make_plan([make_task("a", files_write=["src/utils.py"])])
        risk = compute_risk_score(plan)

        assert risk.auto_approve is True

    def test_no_auto_approve_above_threshold(self) -> None:
        """Test no auto-approve when above threshold."""
        plan = make_plan([
            make_task("a", files_write=["src/auth/secret_key.py"]),  # sensitive
            make_task("b", files_write=["src/payment/billing.py"]),  # sensitive
        ])
        risk = compute_risk_score(plan)

        assert risk.auto_approve is False


class TestRiskScoreStr:
    """Tests for RiskScore string representation."""

    def test_auto_approve_str(self) -> None:
        """Test string for auto-approve."""
        risk = RiskScore(value=10, auto_approve=True)
        assert "AUTO-APPROVE" in str(risk)

    def test_requires_review_str(self) -> None:
        """Test string for requires review."""
        risk = RiskScore(value=50, auto_approve=False)
        assert "REQUIRES REVIEW" in str(risk)


class TestGetRiskSummary:
    """Tests for get_risk_summary."""

    def test_summary_includes_score(self) -> None:
        """Test summary includes score."""
        risk = RiskScore(value=30, auto_approve=False)
        summary = get_risk_summary(risk)

        assert "30" in summary
        assert "REQUIRES REVIEW" in summary

    def test_summary_includes_factors(self) -> None:
        """Test summary includes risk factors."""
        risk = RiskScore(
            value=30,
            factors=["sensitive_path:auth:auth", "many_files:15"],
            auto_approve=False,
        )
        summary = get_risk_summary(risk)

        assert "sensitive_path" in summary
        assert "many_files" in summary
