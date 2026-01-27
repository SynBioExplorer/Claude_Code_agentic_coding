"""Base adapter protocol for framework-specific code generation."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class GeneratedCode:
    """Multi-region output from adapter code generation.

    Adapters produce code for multiple regions of a file:
    - imports: Goes to AUTO:IMPORTS region
    - body: Goes to action-specific region (AUTO:ROUTERS, AUTO:MIDDLEWARE, etc.)
    - config: Goes to AUTO:CONFIG region (if any)
    """

    imports: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)


@dataclass
class AnchorPattern:
    """Defines where to insert region markers in a file.

    When region markers don't exist in a file, anchor patterns
    tell the integrator where to insert them.
    """

    target_files: list[str]  # e.g., ["main.py", "src/main.py", "app.py"]
    anchor_regex: str  # Pattern to find insertion point
    position: str  # "after" | "before"
    fallback: str  # "serialize" | "error" | "end_of_file" | "start_of_file" | "end_of_imports"


@runtime_checkable
class FrameworkAdapter(Protocol):
    """Protocol for framework-specific adapters.

    Adapters provide:
    - Intent schema validation
    - Code generation templates
    - Region marker conventions
    - Implied resource declarations
    """

    @property
    def name(self) -> str:
        """Adapter identifier (e.g., 'fastapi-python', 'express-node')."""
        ...

    @property
    def supported_actions(self) -> set[str]:
        """Set of intent actions this adapter can handle."""
        ...

    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate multi-region code for the given intent.

        Args:
            action: The action type (add_router, add_middleware, etc.)
            intent: Action-specific parameters

        Returns:
            GeneratedCode with imports, body, and optional config.
        """
        ...

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return region markers for each region type.

        Returns:
            Dict mapping region name to (start_marker, end_marker).
            e.g., {"imports": ("# === AUTO:IMPORTS ===", "# === END:IMPORTS ===")}
        """
        ...

    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return anchor patterns for auto-inserting region markers.

        Returns:
            Dict mapping region name to AnchorPattern.
        """
        ...

    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by an intent.

        Args:
            action: The action type
            intent: Action-specific parameters

        Returns:
            List of resource identifiers (e.g., ["route:/auth", "di:AuthService"])
        """
        ...

    def detect_applicability(self, project_root: Path) -> float:
        """Return confidence (0-1) that this adapter applies to the project.

        Args:
            project_root: Root directory of the project

        Returns:
            Confidence score between 0.0 and 1.0
        """
        ...


class BaseAdapter:
    """Base class for framework adapters with common functionality."""

    name: str = "base"
    supported_actions: set[str] = set()

    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate code for an intent. Override in subclasses."""
        if action not in self.supported_actions:
            raise ValueError(f"Unsupported action: {action}")
        return GeneratedCode()

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return region markers. Override in subclasses."""
        return {}

    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return anchor patterns. Override in subclasses."""
        return {}

    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return implied resources. Override in subclasses."""
        return []

    def detect_applicability(self, project_root: Path) -> float:
        """Detect applicability. Override in subclasses."""
        return 0.0


def get_adapter_for_project(
    project_root: Path,
    adapters: list[FrameworkAdapter] | None = None,
) -> FrameworkAdapter | None:
    """Auto-detect the best adapter for a project.

    Args:
        project_root: Root directory of the project
        adapters: List of adapters to try (uses defaults if None)

    Returns:
        Best matching adapter, or None if no adapter matches
    """
    if adapters is None:
        # Import built-in adapters
        from claude_orchestrator.adapters.express import ExpressNodeAdapter
        from claude_orchestrator.adapters.fastapi import FastAPIPythonAdapter
        from claude_orchestrator.adapters.generic import GenericAdapter

        adapters = [
            FastAPIPythonAdapter(),
            ExpressNodeAdapter(),
            GenericAdapter(),
        ]

    best_adapter: FrameworkAdapter | None = None
    best_confidence = 0.0

    for adapter in adapters:
        confidence = adapter.detect_applicability(project_root)
        if confidence > best_confidence:
            best_confidence = confidence
            best_adapter = adapter

    # Require minimum confidence of 0.5
    if best_confidence >= 0.5:
        return best_adapter

    return None
