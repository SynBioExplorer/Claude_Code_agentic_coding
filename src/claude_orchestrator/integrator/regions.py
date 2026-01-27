"""Region marker management for code integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_orchestrator.adapters.base import AnchorPattern, FrameworkAdapter


class RegionNotFoundError(Exception):
    """Raised when region markers are not found in a file."""

    pass


class AnchorNotFoundError(Exception):
    """Raised when anchor pattern is not found for marker insertion."""

    pass


@dataclass
class RegionLocation:
    """Location of a region in a file."""

    start_line: int
    end_line: int
    start_marker: str
    end_marker: str
    content_lines: list[str]


def find_region(
    content: str,
    start_marker: str,
    end_marker: str,
) -> RegionLocation | None:
    """Find a region in file content.

    Args:
        content: File content
        start_marker: Region start marker
        end_marker: Region end marker

    Returns:
        RegionLocation if found, None otherwise
    """
    lines = content.split("\n")
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if start_marker in line and start_idx is None:
            start_idx = i
        elif end_marker in line and start_idx is not None:
            end_idx = i
            break

    if start_idx is not None and end_idx is not None:
        content_lines = lines[start_idx + 1 : end_idx]
        return RegionLocation(
            start_line=start_idx,
            end_line=end_idx,
            start_marker=start_marker,
            end_marker=end_marker,
            content_lines=content_lines,
        )

    return None


def find_all_regions(
    content: str,
    markers: dict[str, tuple[str, str]],
) -> dict[str, RegionLocation]:
    """Find all regions in file content.

    Args:
        content: File content
        markers: Dict of region_name -> (start_marker, end_marker)

    Returns:
        Dict of region_name -> RegionLocation
    """
    regions: dict[str, RegionLocation] = {}

    for name, (start, end) in markers.items():
        region = find_region(content, start, end)
        if region:
            regions[name] = region

    return regions


def insert_markers(
    content: str,
    start_marker: str,
    end_marker: str,
    anchor: AnchorPattern,
) -> str:
    """Insert region markers at the anchor location.

    Args:
        content: File content
        start_marker: Region start marker
        end_marker: Region end marker
        anchor: Anchor pattern for insertion

    Returns:
        Modified content with markers inserted

    Raises:
        AnchorNotFoundError: If anchor pattern not found and fallback is "serialize" or "error"
    """
    lines = content.split("\n")

    # Find anchor
    anchor_idx = None
    for i, line in enumerate(lines):
        if re.search(anchor.anchor_regex, line):
            anchor_idx = i
            if anchor.position == "after":
                anchor_idx += 1
            break

    if anchor_idx is None:
        # Apply fallback behavior
        if anchor.fallback == "serialize" or anchor.fallback == "error":
            raise AnchorNotFoundError(
                f"Anchor pattern not found: {anchor.anchor_regex}. "
                f"Hot file will use serialization."
            )
        elif anchor.fallback == "end_of_file":
            anchor_idx = len(lines)
        elif anchor.fallback == "start_of_file":
            anchor_idx = 0
        elif anchor.fallback == "end_of_imports":
            # Find last import statement
            anchor_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    anchor_idx = i + 1
                # Also handle JS-style imports
                elif stripped.startswith("const ") and "require(" in stripped:
                    anchor_idx = i + 1
        else:
            anchor_idx = len(lines)

    # Insert markers
    marker_block = [
        "",
        start_marker,
        end_marker,
        "",
    ]

    result_lines = lines[:anchor_idx] + marker_block + lines[anchor_idx:]
    return "\n".join(result_lines)


def ensure_region_markers(
    content: str,
    regions_needed: set[str],
    adapter: FrameworkAdapter,
) -> str:
    """Ensure all needed region markers exist in the content.

    Args:
        content: File content
        regions_needed: Set of region names needed
        adapter: Framework adapter with markers and anchors

    Returns:
        Modified content with all markers present
    """
    markers = adapter.get_region_markers()
    anchors = adapter.get_anchor_patterns()

    for region in regions_needed:
        if region not in markers:
            continue

        start_marker, end_marker = markers[region]

        # Check if markers already exist
        if start_marker in content:
            continue

        # Try to insert using anchor
        if region in anchors:
            try:
                content = insert_markers(
                    content, start_marker, end_marker, anchors[region]
                )
            except AnchorNotFoundError:
                # Log warning but continue - operation will need serialization
                pass

    return content


def insert_into_region(
    content: str,
    start_marker: str,
    end_marker: str,
    new_lines: list[str],
    deduplicate: bool = True,
) -> str:
    """Insert lines into a marked region.

    Args:
        content: File content
        start_marker: Region start marker
        end_marker: Region end marker
        new_lines: Lines to insert
        deduplicate: Remove duplicate lines

    Returns:
        Modified content with lines inserted

    Raises:
        RegionNotFoundError: If region markers not found
    """
    region = find_region(content, start_marker, end_marker)

    if region is None:
        raise RegionNotFoundError(
            f"Region markers not found: {start_marker} ... {end_marker}"
        )

    lines = content.split("\n")

    if deduplicate:
        # Get existing lines (stripped for comparison)
        existing_set = {
            line.strip() for line in region.content_lines if line.strip()
        }

        # Filter out duplicates
        new_lines = [
            line for line in new_lines if line.strip() and line.strip() not in existing_set
        ]

    # Insert new lines before end marker
    result_lines = (
        lines[: region.end_line] + new_lines + lines[region.end_line :]
    )

    return "\n".join(result_lines)


def get_region_content(
    content: str,
    start_marker: str,
    end_marker: str,
) -> list[str]:
    """Get the content within a region.

    Args:
        content: File content
        start_marker: Region start marker
        end_marker: Region end marker

    Returns:
        List of lines within the region, or empty list if not found
    """
    region = find_region(content, start_marker, end_marker)
    if region:
        return region.content_lines
    return []


def remove_from_region(
    content: str,
    start_marker: str,
    end_marker: str,
    lines_to_remove: list[str],
) -> str:
    """Remove specific lines from a region.

    Args:
        content: File content
        start_marker: Region start marker
        end_marker: Region end marker
        lines_to_remove: Lines to remove (matched by stripped content)

    Returns:
        Modified content with lines removed
    """
    region = find_region(content, start_marker, end_marker)

    if region is None:
        return content

    lines = content.split("\n")
    remove_set = {line.strip() for line in lines_to_remove}

    # Filter out lines to remove
    new_region_content = [
        line
        for line in region.content_lines
        if line.strip() not in remove_set
    ]

    # Reconstruct file
    result_lines = (
        lines[: region.start_line + 1]
        + new_region_content
        + lines[region.end_line :]
    )

    return "\n".join(result_lines)
