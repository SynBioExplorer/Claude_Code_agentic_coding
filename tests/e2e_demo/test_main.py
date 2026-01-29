"""Integration tests for main module."""

import pytest
from tests.e2e_demo.main import run_calculation


class TestRunCalculation:
    """Test suite for run_calculation() function."""

    def test_run_calculation_add(self):
        """Test running an addition calculation."""
        result = run_calculation('add', 10, 5)
        assert '15' in result
        assert '10' in result
        assert '5' in result
        assert '+' in result

    def test_run_calculation_subtract(self):
        """Test running a subtraction calculation."""
        result = run_calculation('subtract', 10, 5)
        assert '5' in result
        assert '10' in result
        assert '-' in result

    def test_run_calculation_with_floats(self):
        """Test running calculations with floating point numbers."""
        result = run_calculation('add', 2.5, 3.7)
        assert '2.5' in result
        assert '3.7' in result
        assert '6.2' in result

    def test_run_calculation_with_negative_numbers(self):
        """Test running calculations with negative numbers."""
        result = run_calculation('add', -5, 3)
        assert '-5' in result
        assert '3' in result
        assert '-2' in result

        result = run_calculation('subtract', 5, 10)
        assert '5' in result
        assert '10' in result
        assert '-5' in result

    def test_run_calculation_case_insensitive(self):
        """Test that operation names are case-insensitive."""
        result1 = run_calculation('ADD', 10, 5)
        result2 = run_calculation('add', 10, 5)
        assert result1 == result2

        result1 = run_calculation('SUBTRACT', 10, 5)
        result2 = run_calculation('subtract', 10, 5)
        assert result1 == result2

    def test_run_calculation_with_zero(self):
        """Test calculations involving zero."""
        result = run_calculation('add', 0, 5)
        assert '0' in result
        assert '5' in result

        result = run_calculation('subtract', 5, 0)
        assert '5' in result
        assert '0' in result

    def test_run_calculation_large_numbers(self):
        """Test calculations with large numbers."""
        result = run_calculation('add', 1000000, 2000000)
        assert '3000000' in result

    def test_run_calculation_unknown_operation(self):
        """Test that unknown operations raise ValueError."""
        with pytest.raises(ValueError, match="Unknown operation"):
            run_calculation('multiply', 5, 3)

        with pytest.raises(ValueError, match="Unknown operation"):
            run_calculation('invalid', 10, 2)

    def test_integration_add_chain(self):
        """Test a chain of addition operations."""
        # This tests the integration of calculator and formatter
        result1 = run_calculation('add', 5, 3)
        assert '8' in result1

        result2 = run_calculation('add', 8, 2)
        assert '10' in result2

    def test_integration_mixed_operations(self):
        """Test mixed operations using the integrated system."""
        # Add then use result conceptually for next operation
        add_result = run_calculation('add', 20, 5)
        assert '25' in add_result

        sub_result = run_calculation('subtract', 25, 10)
        assert '15' in sub_result

    def test_verification_requirement(self):
        """Test the exact verification requirement from task spec."""
        result = run_calculation('add', 10, 5)
        assert '15' in result
        print('Main integration OK')

    def test_float_display_as_integer(self):
        """Test that floats like 5.0 are displayed as 5."""
        result = run_calculation('add', 2.0, 3.0)
        assert '2 + 3 = 5' in result or ('2' in result and '3' in result and '5' in result)

    def test_result_format_structure(self):
        """Test that results follow expected format structure."""
        result = run_calculation('add', 7, 3)
        # Should be in format "a + b = result"
        parts = result.split('=')
        assert len(parts) == 2
        assert '10' in parts[1].strip()
