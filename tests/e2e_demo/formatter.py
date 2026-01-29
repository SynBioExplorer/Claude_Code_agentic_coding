"""Formatter module for formatting calculation results.

This module implements the FormatterProtocol contract (version: 804534f).
"""

from typing import Union


def format_result(operation: str, a: Union[int, float], b: Union[int, float], result: Union[int, float]) -> str:
    """Format a calculation result as a human-readable string.

    Args:
        operation: The operation performed (e.g., 'add', 'subtract', 'multiply', 'divide')
        a: First operand
        b: Second operand
        result: The calculation result

    Returns:
        A formatted string describing the calculation

    Examples:
        >>> format_result('add', 2, 3, 5)
        '2 + 3 = 5'
        >>> format_result('subtract', 10, 4, 6)
        '10 - 4 = 6'
        >>> format_result('multiply', 3, 7, 21)
        '3 × 7 = 21'
    """
    # Map operation names to symbols
    operation_symbols = {
        'add': '+',
        'subtract': '-',
        'multiply': '×',
        'divide': '÷',
        'power': '^',
        'modulo': '%'
    }

    # Get the symbol (default to the operation name if not found)
    operation_lower = operation.lower()
    symbol = operation_symbols.get(operation_lower, operation)

    # Format numbers - show integers without decimal point
    def format_number(n: Union[int, float]) -> str:
        if isinstance(n, float) and n.is_integer():
            return str(int(n))
        return str(n)

    a_str = format_number(a)
    b_str = format_number(b)
    result_str = format_number(result)

    return f"{a_str} {symbol} {b_str} = {result_str}"
