"""Generic fallback adapter for basic operations."""

from __future__ import annotations

from pathlib import Path

from claude_orchestrator.adapters.base import AnchorPattern, BaseAdapter, GeneratedCode


class GenericAdapter(BaseAdapter):
    """Fallback adapter for projects without a specific framework adapter.

    Provides basic operations that work with any codebase:
    - add_import: Add an import statement
    - append_to_list: Append an item to a list/array

    When no framework-specific adapter matches, this adapter is used.
    It serializes operations (no parallel hot file modifications).
    """

    name = "generic"

    supported_actions = {
        "add_import",
        "append_to_list",
        "add_line",
    }

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return generic region markers.

        These use a language-agnostic comment style that works in many languages.
        """
        return {
            "imports": ("# === AUTO:IMPORTS ===", "# === END:IMPORTS ==="),
            "body": ("# === AUTO:BODY ===", "# === END:BODY ==="),
        }

    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return generic anchor patterns.

        For the generic adapter, we don't auto-insert markers.
        Files must have markers pre-existing or operations fall back to serialization.
        """
        return {}

    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate code for a generic intent."""
        if action not in self.supported_actions:
            raise ValueError(f"Unsupported action: {action}")

        if action == "add_import":
            return self._generate_import(intent)
        elif action == "append_to_list":
            return self._generate_list_append(intent)
        elif action == "add_line":
            return self._generate_line(intent)

        return GeneratedCode()

    def _generate_import(self, intent: dict) -> GeneratedCode:
        """Generate an import statement."""
        import_line = intent["import_line"]
        return GeneratedCode(imports=[import_line])

    def _generate_list_append(self, intent: dict) -> GeneratedCode:
        """Generate a list append operation.

        For Python-style lists, this generates a list item.
        The actual insertion is handled by the integrator.
        """
        item = intent["item"]
        return GeneratedCode(body=[f"    {item},"])

    def _generate_line(self, intent: dict) -> GeneratedCode:
        """Generate a generic line of code."""
        line = intent["line"]
        region = intent.get("region", "body")

        if region == "imports":
            return GeneratedCode(imports=[line])
        elif region == "config":
            return GeneratedCode(config=[line])
        else:
            return GeneratedCode(body=[line])

    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by this intent.

        Generic adapter doesn't imply resources by default.
        """
        return []

    def detect_applicability(self, project_root: Path) -> float:
        """Generic adapter always has minimal applicability.

        It's used as a fallback when no other adapter matches.
        """
        return 0.1  # Low confidence, used as fallback


class PythonGenericAdapter(GenericAdapter):
    """Python-specific generic adapter."""

    name = "python-generic"

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return Python-style region markers."""
        return {
            "imports": ("# === AUTO:IMPORTS ===", "# === END:IMPORTS ==="),
            "body": ("# === AUTO:BODY ===", "# === END:BODY ==="),
            "config": ("# === AUTO:CONFIG ===", "# === END:CONFIG ==="),
        }

    def detect_applicability(self, project_root: Path) -> float:
        """Detect if this is a Python project."""
        confidence = 0.0

        # Check for Python project indicators
        if (project_root / "pyproject.toml").exists():
            confidence += 0.3
        if (project_root / "setup.py").exists():
            confidence += 0.2
        if (project_root / "requirements.txt").exists():
            confidence += 0.2

        # Check for Python files
        py_files = list(project_root.glob("**/*.py"))
        if py_files:
            confidence += 0.2

        return min(confidence, 0.4)  # Cap at 0.4, let specific adapters win


class JavaScriptGenericAdapter(GenericAdapter):
    """JavaScript/TypeScript-specific generic adapter."""

    name = "javascript-generic"

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return JavaScript-style region markers."""
        return {
            "imports": ("// === AUTO:IMPORTS ===", "// === END:IMPORTS ==="),
            "body": ("// === AUTO:BODY ===", "// === END:BODY ==="),
            "config": ("// === AUTO:CONFIG ===", "// === END:CONFIG ==="),
        }

    def detect_applicability(self, project_root: Path) -> float:
        """Detect if this is a JavaScript/TypeScript project."""
        confidence = 0.0

        # Check for Node.js project indicators
        if (project_root / "package.json").exists():
            confidence += 0.3

        # Check for TypeScript
        if (project_root / "tsconfig.json").exists():
            confidence += 0.2

        # Check for JS/TS files
        js_files = list(project_root.glob("**/*.js")) + list(project_root.glob("**/*.ts"))
        if js_files:
            confidence += 0.2

        return min(confidence, 0.4)  # Cap at 0.4, let specific adapters win
