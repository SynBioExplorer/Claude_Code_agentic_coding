"""Pydantic models for .claude-agents.yaml configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Model configuration for agents."""

    planner_model: str = Field(default="opus", description="Model for Planner-Architect")
    supervisor_model: str = Field(default="sonnet", description="Model for Supervisor")
    worker_model: str = Field(default="sonnet", description="Model for Workers")
    verifier_model: str = Field(default="sonnet", description="Model for Verifier")


class OrchestrationSettings(BaseModel):
    """Orchestration settings."""

    planner_model: str = Field(default="opus")
    supervisor_model: str = Field(default="sonnet")
    worker_model: str = Field(default="sonnet")
    verifier_model: str = Field(default="sonnet")
    max_parallel_workers: int = Field(default=5)
    max_iterations: int = Field(default=3)
    merge_strategy: str = Field(default="merge_bubble")
    worktree_dir: str = Field(default=".worktrees")


class SensitivePattern(BaseModel):
    """Pattern for sensitive file detection."""

    pattern: str = Field(..., description="Regex pattern to match")
    weight: int = Field(..., description="Risk weight for this pattern")


class ApprovalSettings(BaseModel):
    """Settings for approval gates."""

    auto_approve_threshold: int = Field(
        default=25, description="Max risk score for auto-approval"
    )
    sensitive_patterns: list[SensitivePattern] = Field(
        default_factory=lambda: [
            SensitivePattern(pattern="auth|security|crypto", weight=20),
            SensitivePattern(pattern="payment|billing", weight=25),
            SensitivePattern(pattern="prod|deploy", weight=30),
            SensitivePattern(pattern="migration|schema", weight=15),
        ]
    )
    always_require_human: list[str] = Field(
        default_factory=lambda: ["**/.env*", "**/migrations/**", "**/secrets/**"]
    )


class TemplateResolution(BaseModel):
    """Settings for template resolution in verification commands."""

    test_file_patterns: list[str] = Field(
        default_factory=lambda: [
            "tests/test_{basename}.py",
            "tests/{basename}_test.py",
            "**/*_test.py",
        ]
    )
    fallback_on_no_match: str = Field(default="tests/")


class VerificationSettings(BaseModel):
    """Verification settings."""

    require_executable_checks: bool = Field(default=True)
    min_checks_per_task: int = Field(default=1)
    template_resolution: TemplateResolution = Field(
        default_factory=TemplateResolution
    )


class BoundarySettings(BaseModel):
    """Boundary enforcement settings."""

    enforce_via_git_diff: bool = Field(default=True)
    reject_excessive_churn: bool = Field(default=True)
    churn_threshold_lines: int = Field(default=500)
    reject_formatting_churn: bool = Field(default=True)
    formatting_check_allowlist: list[str] = Field(
        default_factory=lambda: [
            ".js", ".ts", ".jsx", ".tsx", ".json", ".css", ".html", ".java", ".go", ".rs"
        ]
    )
    formatting_check_denylist: list[str] = Field(
        default_factory=lambda: [".py", ".yaml", ".yml", ".mk", "Makefile"]
    )
    forbidden_patterns: list[str] = Field(
        default_factory=lambda: [
            r"node_modules/",
            r"__pycache__/",
            r"vendor/",
            r"dist/",
            r"build/",
            r"\.generated\.",
            r"\.min\.(js|css)$",
        ]
    )


class HotFileConfig(BaseModel):
    """Configuration for a hot file."""

    path: str = Field(..., description="Path to the hot file")
    actions: list[str] = Field(..., description="Allowed actions for this file")


class PatchIntentSettings(BaseModel):
    """Settings for patch intents and framework adapters."""

    enabled: bool = Field(default=True)
    adapter: str = Field(default="auto")
    hot_files: list[HotFileConfig] = Field(default_factory=list)
    fallback: str = Field(default="serialize")
    region_markers: dict[str, Any] = Field(
        default_factory=lambda: {"auto_insert": True, "style": "comment"}
    )


class ResourceSettings(BaseModel):
    """Resource conflict detection settings."""

    enabled: bool = Field(default=True)
    auto_emit_from_intents: bool = Field(default=True)


class EcosystemConfig(BaseModel):
    """Configuration for a package ecosystem."""

    manager: str = Field(..., description="Package manager (npm, pnpm, uv, etc.)")
    manifest: str = Field(..., description="Manifest file (package.json, pyproject.toml)")
    lockfile: str = Field(..., description="Lockfile (pnpm-lock.yaml, uv.lock)")


class DependencySettings(BaseModel):
    """Dependency management settings."""

    install_phase: str = Field(default="stage_0.5")
    detect_conflicts_early: bool = Field(default=True)
    allow_worker_installs: bool = Field(default=False)
    verify_env_hash: bool = Field(default=True)
    ecosystems: dict[str, EcosystemConfig] = Field(default_factory=dict)


class ContractSettings(BaseModel):
    """Contract management settings."""

    version_enforcement: bool = Field(default=True)
    max_renegotiations: int = Field(default=2)
    track_renegotiations: bool = Field(default=True)


class QualityCheck(BaseModel):
    """A quality check command."""

    name: str | None = Field(default=None)
    command: str = Field(...)
    required: bool = Field(default=True)


class QualitySettings(BaseModel):
    """Quality gate settings."""

    verifier_checks: list[str] = Field(
        default_factory=lambda: [
            "pytest {modified_tests}",
            "ruff check {modified_files}",
            "mypy {modified_files}",
        ]
    )
    post_merge_checks: list[str] = Field(
        default_factory=lambda: ["pytest", "ruff check ."]
    )


class BarrierCheck(BaseModel):
    """A phase barrier check."""

    name: str
    command: str
    required: bool = Field(default=True)


class PhaseSettings(BaseModel):
    """Phase barrier settings."""

    stabilization_gate: bool = Field(default=True)
    barrier_checks: list[BarrierCheck] = Field(default_factory=list)


class OrchestrationConfig(BaseModel):
    """Complete configuration for .claude-agents.yaml."""

    orchestration: OrchestrationSettings = Field(
        default_factory=OrchestrationSettings
    )
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    boundaries: BoundarySettings = Field(default_factory=BoundarySettings)
    patch_intents: PatchIntentSettings = Field(default_factory=PatchIntentSettings)
    resources: ResourceSettings = Field(default_factory=ResourceSettings)
    dependencies: DependencySettings = Field(default_factory=DependencySettings)
    contracts: ContractSettings = Field(default_factory=ContractSettings)
    quality: QualitySettings = Field(default_factory=QualitySettings)
    phases: PhaseSettings = Field(default_factory=PhaseSettings)

    @classmethod
    def load(cls, path: str | Path) -> "OrchestrationConfig":
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def save(self, path: str | Path) -> None:
        """Save configuration to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    def get_lockfile_patterns(self) -> list[str]:
        """Get regex patterns for all configured lockfiles."""
        import re

        patterns: list[str] = []

        # From ecosystem config
        for eco_config in self.dependencies.ecosystems.values():
            lockfile = eco_config.lockfile
            if lockfile:
                escaped = re.escape(lockfile)
                patterns.append(f"(^|/){escaped}$")

        # Common lockfiles as fallback
        common_lockfiles = [
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "uv.lock",
            "poetry.lock",
            "requirements.lock",
            "Pipfile.lock",
            "Cargo.lock",
            "go.sum",
            "Gemfile.lock",
            "packages.lock.json",
            "composer.lock",
        ]

        for lockfile in common_lockfiles:
            escaped = re.escape(lockfile)
            pattern = f"(^|/){escaped}$"
            if pattern not in patterns:
                patterns.append(pattern)

        return patterns
