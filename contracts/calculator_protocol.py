"""
CalculatorProtocol - Interface contract for calculator module
Version: 804534f
"""
from typing import Protocol


class CalculatorProtocol(Protocol):
    """Protocol defining the calculator interface."""

    def add(self, a: float, b: float) -> float:
        """Add two numbers and return the result."""
        ...

    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a and return the result."""
        ...
