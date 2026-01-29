"""Main module that integrates calculator and formatter.

This module ties together the calculator and formatter modules to provide
a complete calculation and formatting pipeline.
"""

from tests.e2e_demo.calculator import add, subtract
from tests.e2e_demo.formatter import format_result


def run_calculation(operation: str, a: int | float, b: int | float) -> str:
    """Run a calculation and return a formatted result.

    Args:
        operation: The operation to perform ('add' or 'subtract')
        a: First operand
        b: Second operand

    Returns:
        A formatted string describing the calculation and result

    Raises:
        ValueError: If operation is not recognized

    Examples:
        >>> run_calculation('add', 10, 5)
        '10 + 5 = 15'
        >>> run_calculation('subtract', 10, 5)
        '10 - 5 = 5'
    """
    operation_lower = operation.lower()

    if operation_lower == 'add':
        result = add(a, b)
    elif operation_lower == 'subtract':
        result = subtract(a, b)
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return format_result(operation, a, b, result)


def main():
    """Main entry point demonstrating the calculator and formatter integration."""
    # Demonstrate addition
    print("Addition Examples:")
    print(run_calculation('add', 10, 5))
    print(run_calculation('add', 2.5, 3.7))
    print(run_calculation('add', -5, 3))

    print("\nSubtraction Examples:")
    print(run_calculation('subtract', 10, 5))
    print(run_calculation('subtract', 20.5, 8.3))
    print(run_calculation('subtract', 5, 10))


if __name__ == "__main__":
    main()
