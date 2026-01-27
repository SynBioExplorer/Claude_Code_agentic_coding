"""Pydantic models for tasks.yaml task specifications."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class VerificationType(str, Enum):
    """Type of verification check."""

    TEST = "test"
    LINT = "lint"
    TYPECHECK = "typecheck"
    CUSTOM = "custom"


class VerificationCheck(BaseModel):
    """A single verification check for a task."""

    command: str = Field(..., description="Command to execute for verification")
    type: VerificationType = Field(
        default=VerificationType.CUSTOM, description="Type of verification check"
    )
    required: bool = Field(default=True, description="Whether this check must pass")
    description: str | None = Field(default=None, description="Human-readable description")


class PatchIntent(BaseModel):
    """A structured patch intent for hot files."""

    file: str = Field(..., description="Target file for the intent")
    action: str = Field(..., description="Action type (add_router, add_middleware, etc.)")
    intent: dict[str, Any] = Field(
        default_factory=dict, description="Action-specific parameters"
    )


class DependencySpec(BaseModel):
    """Dependencies required by a task."""

    runtime: list[str] = Field(default_factory=list, description="Runtime dependencies")
    dev: list[str] = Field(default_factory=list, description="Development dependencies")


class TaskSpec(BaseModel):
    """Specification for a single task in the execution plan."""

    id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="Human-readable task description")

    # File ownership
    files_write: list[str] = Field(
        default_factory=list, description="Files this task is allowed to write"
    )
    files_read: list[str] = Field(
        default_factory=list, description="Files this task may read"
    )
    files_append: list[str] = Field(
        default_factory=list, description="Files this task may append to"
    )

    # Resource ownership
    resources_write: list[str] = Field(
        default_factory=list,
        description="Logical resources this task claims (routes, DI bindings, config keys)",
    )
    resources_read: list[str] = Field(
        default_factory=list, description="Logical resources this task reads"
    )

    # Dependencies
    depends_on: list[str] = Field(
        default_factory=list, description="Task IDs that must complete before this task"
    )

    # Verification (REQUIRED - at least one check)
    verification: list[VerificationCheck] = Field(
        ..., min_length=1, description="Verification checks for this task"
    )

    # Structured patch intents for hot files
    patch_intents: list[PatchIntent] = Field(
        default_factory=list, description="Structured intents for hot files"
    )

    # Dependencies required by this task
    deps_required: DependencySpec | None = Field(
        default=None, description="Package dependencies needed by this task"
    )

    # Options
    allow_large_changes: bool = Field(
        default=False, description="Allow changes exceeding churn threshold"
    )

    @field_validator("verification", mode="before")
    @classmethod
    def ensure_verification_not_empty(cls, v: list[Any]) -> list[Any]:
        """Ensure at least one verification check is defined."""
        if not v:
            raise ValueError(
                "Every task MUST have at least one verification command. "
                "Define at least one check in 'verification'."
            )
        return v


class ContractSpec(BaseModel):
    """Interface contract specification."""

    name: str = Field(..., description="Contract name (e.g., AuthServiceProtocol)")
    version: str = Field(..., description="Version hash (commit hash when created)")
    file_path: str = Field(..., description="Path to contract file in contracts/")
    methods: list[str] = Field(default_factory=list, description="Method signatures")
    created_at: str = Field(..., description="ISO timestamp when contract was created")
    consumers: list[str] = Field(
        default_factory=list, description="Task IDs that depend on this contract"
    )


class ExecutionPlan(BaseModel):
    """Complete execution plan for a multi-task operation."""

    request: str = Field(..., description="Original user request")
    tasks: list[TaskSpec] = Field(..., description="List of tasks to execute")
    contracts: list[ContractSpec] = Field(
        default_factory=list, description="Interface contracts for cross-task dependencies"
    )
    parallel_waves: list[list[str]] = Field(
        default_factory=list, description="Task IDs grouped by parallel execution wave"
    )
    risk_score: int = Field(default=0, description="Computed risk score for approval")
    risk_factors: list[str] = Field(
        default_factory=list, description="Factors contributing to risk score"
    )
    auto_approve: bool = Field(
        default=False, description="Whether plan qualifies for auto-approval"
    )
    created_at: str = Field(..., description="ISO timestamp when plan was created")
