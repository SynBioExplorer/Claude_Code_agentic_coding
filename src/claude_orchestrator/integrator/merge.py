"""Code merging and intent application for hot files."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from claude_orchestrator.integrator.regions import (
    RegionNotFoundError,
    ensure_region_markers,
    find_region,
    insert_into_region,
)

if TYPE_CHECKING:
    from claude_orchestrator.adapters.base import FrameworkAdapter, GeneratedCode


@dataclass
class IntentApplication:
    """Record of an intent application."""

    action: str
    intent: dict
    success: bool
    error: str | None = None


@dataclass
class MergeResult:
    """Result of applying intents to a file."""

    file_path: str
    success: bool
    modified_content: str | None = None
    applications: list[IntentApplication] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Mapping from action to body region name
ACTION_REGION_MAP: dict[str, str] = {
    "add_router": "routers",
    "add_middleware": "middleware",
    "add_dependency": "dependencies",
    "add_config": "config",
}


class Integrator:
    """Routes generated code to appropriate regions in hot files."""

    def __init__(self, adapter: FrameworkAdapter):
        """Initialize the integrator with a framework adapter.

        Args:
            adapter: Framework adapter for code generation
        """
        self.adapter = adapter
        self.markers = adapter.get_region_markers()

    def apply_intents(
        self,
        file_path: str | Path,
        intents: list[dict],
    ) -> MergeResult:
        """Apply all intents to a file, routing generated code to correct regions.

        Args:
            file_path: Path to the hot file
            intents: List of intent dictionaries with 'action' and 'intent' keys

        Returns:
            MergeResult with modified content and application records
        """
        path = Path(file_path)
        result = MergeResult(file_path=str(file_path), success=True)

        try:
            content = path.read_text()
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to read file: {e}")
            return result

        # Collect all generated code
        all_imports: list[str] = []
        body_by_region: dict[str, list[str]] = defaultdict(list)
        config_lines: list[str] = []

        for intent_data in intents:
            action = intent_data.get("action", "")
            intent = intent_data.get("intent", {})

            application = IntentApplication(action=action, intent=intent, success=False)

            try:
                generated = self.adapter.generate_code(action, intent)

                # Collect imports
                all_imports.extend(generated.imports)

                # Collect body lines, routed to correct region
                region = self._get_body_region(action)
                body_by_region[region].extend(generated.body)

                # Collect config
                config_lines.extend(generated.config)

                application.success = True

            except Exception as e:
                application.error = str(e)
                result.errors.append(f"Failed to generate code for {action}: {e}")

            result.applications.append(application)

        # Determine which regions we need
        regions_needed = {"imports"} if all_imports else set()
        regions_needed.update(body_by_region.keys())
        if config_lines and "config" in self.markers:
            regions_needed.add("config")

        # Ensure region markers exist
        try:
            content = ensure_region_markers(content, regions_needed, self.adapter)
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to ensure region markers: {e}")
            return result

        # Insert imports
        if all_imports and "imports" in self.markers:
            try:
                content = insert_into_region(
                    content,
                    self.markers["imports"][0],
                    self.markers["imports"][1],
                    all_imports,
                )
            except RegionNotFoundError as e:
                result.errors.append(f"Failed to insert imports: {e}")

        # Insert body lines into their respective regions
        for region, lines in body_by_region.items():
            if lines and region in self.markers:
                try:
                    content = insert_into_region(
                        content,
                        self.markers[region][0],
                        self.markers[region][1],
                        lines,
                    )
                except RegionNotFoundError as e:
                    result.errors.append(f"Failed to insert into {region}: {e}")

        # Insert config
        if config_lines and "config" in self.markers:
            try:
                content = insert_into_region(
                    content,
                    self.markers["config"][0],
                    self.markers["config"][1],
                    config_lines,
                )
            except RegionNotFoundError as e:
                result.errors.append(f"Failed to insert config: {e}")

        result.modified_content = content

        # Mark as failed if any critical errors
        if result.errors and not all(app.success for app in result.applications):
            result.success = False

        return result

    def _get_body_region(self, action: str) -> str:
        """Map action to body region name.

        Args:
            action: Intent action type

        Returns:
            Region name for the action's body code
        """
        return ACTION_REGION_MAP.get(action, "body")

    def apply_and_write(
        self,
        file_path: str | Path,
        intents: list[dict],
    ) -> MergeResult:
        """Apply intents and write the modified content back to file.

        Args:
            file_path: Path to the hot file
            intents: List of intent dictionaries

        Returns:
            MergeResult with application status
        """
        result = self.apply_intents(file_path, intents)

        if result.success and result.modified_content is not None:
            try:
                Path(file_path).write_text(result.modified_content)
            except Exception as e:
                result.success = False
                result.errors.append(f"Failed to write file: {e}")

        return result


def deduplicate_region(lines: list[str]) -> list[str]:
    """Remove duplicate lines while preserving order.

    Args:
        lines: List of code lines

    Returns:
        Deduplicated list preserving first occurrence
    """
    seen: set[str] = set()
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            result.append(line)
        elif not stripped:
            # Preserve empty lines
            result.append(line)

    return result


def merge_region_content(
    existing: list[str],
    new: list[str],
    deduplicate: bool = True,
) -> list[str]:
    """Merge new content into existing region content.

    Args:
        existing: Existing lines in the region
        new: New lines to add
        deduplicate: Whether to deduplicate

    Returns:
        Merged content
    """
    if deduplicate:
        existing_set = {line.strip() for line in existing if line.strip()}
        filtered_new = [
            line for line in new if line.strip() and line.strip() not in existing_set
        ]
        return existing + filtered_new
    else:
        return existing + new
