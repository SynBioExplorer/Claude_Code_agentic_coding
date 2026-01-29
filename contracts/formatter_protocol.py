"""
FormatterProtocol - Interface contract for formatter module
Version: 804534f
"""
from typing import Protocol


class FormatterProtocol(Protocol):
    """Protocol defining the formatter interface."""

    def format_result(self, operation: str, a: float, b: float, result: float) -> str:
        """Format a calculation result into a human-readable string."""
        ...
