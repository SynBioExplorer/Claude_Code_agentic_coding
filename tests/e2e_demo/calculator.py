"""Calculator module providing basic arithmetic operations.

This module implements the CalculatorProtocol contract (version: 804534f).
"""

def add(a: int | float, b: int | float) -> int | float:
    """Add two numbers together.

    Args:
        a: First number (integer or float)
        b: Second number (integer or float)

    Returns:
        The sum of a and b

    Examples:
        >>> add(2, 3)
        5
        >>> add(2.5, 3.7)
        6.2
    """
    return a + b


def subtract(a: int | float, b: int | float) -> int | float:
    """Subtract b from a.

    Args:
        a: Number to subtract from (integer or float)
        b: Number to subtract (integer or float)

    Returns:
        The difference of a - b

    Examples:
        >>> subtract(5, 2)
        3
        >>> subtract(10.5, 3.2)
        7.3
    """
    return a - b
