"""Unit tests for formatter module."""

import pytest
from tests.e2e_demo.formatter import format_result


class TestFormatResult:
    """Test suite for format_result() function."""

    def test_format_add(self):
        """Test formatting addition operations."""
        result = format_result('add', 2, 3, 5)
        assert result == '2 + 3 = 5'
        assert '2' in result
        assert '3' in result
        assert '5' in result

    def test_format_subtract(self):
        """Test formatting subtraction operations."""
        result = format_result('subtract', 10, 4, 6)
        assert result == '10 - 4 = 6'

    def test_format_multiply(self):
        """Test formatting multiplication operations."""
        result = format_result('multiply', 3, 7, 21)
        assert result == '3 × 7 = 21'

    def test_format_divide(self):
        """Test formatting division operations."""
        result = format_result('divide', 10, 2, 5)
        assert result == '10 ÷ 2 = 5'

    def test_format_with_floats(self):
        """Test formatting with floating point numbers."""
        result = format_result('add', 2.5, 3.7, 6.2)
        assert result == '2.5 + 3.7 = 6.2'

    def test_format_with_float_that_is_integer(self):
        """Test that floats like 5.0 are displayed as 5."""
        result = format_result('add', 2.0, 3.0, 5.0)
        assert result == '2 + 3 = 5'

    def test_format_with_negative_numbers(self):
        """Test formatting with negative numbers."""
        result = format_result('add', -5, 3, -2)
        assert result == '-5 + 3 = -2'

        result = format_result('subtract', 5, -3, 8)
        assert result == '5 - -3 = 8'

    def test_format_with_zero(self):
        """Test formatting with zero."""
        result = format_result('add', 0, 5, 5)
        assert result == '0 + 5 = 5'

        result = format_result('subtract', 5, 0, 5)
        assert result == '5 - 0 = 5'

    def test_format_large_numbers(self):
        """Test formatting large numbers."""
        result = format_result('add', 1000000, 2000000, 3000000)
        assert result == '1000000 + 2000000 = 3000000'

    def test_format_case_insensitive(self):
        """Test that operation names are case-insensitive."""
        result1 = format_result('ADD', 2, 3, 5)
        result2 = format_result('add', 2, 3, 5)
        assert result1 == result2

    def test_format_unknown_operation(self):
        """Test formatting with unknown operation (uses operation name as symbol)."""
        result = format_result('custom_op', 5, 3, 8)
        assert '5' in result
        assert '3' in result
        assert '8' in result
        assert 'custom_op' in result

    def test_format_power(self):
        """Test formatting power operations."""
        result = format_result('power', 2, 3, 8)
        assert result == '2 ^ 3 = 8'

    def test_format_modulo(self):
        """Test formatting modulo operations."""
        result = format_result('modulo', 10, 3, 1)
        assert result == '10 % 3 = 1'

    def test_mixed_int_and_float(self):
        """Test formatting with mixed integer and float inputs."""
        result = format_result('add', 2, 3.5, 5.5)
        assert result == '2 + 3.5 = 5.5'

    def test_format_contains_all_values(self):
        """Test that formatted string contains all input values."""
        a, b, res = 10, 5, 15
        result = format_result('add', a, b, res)
        assert str(a) in result
        assert str(b) in result
        assert str(res) in result

    def test_format_decimal_precision(self):
        """Test that decimal precision is preserved."""
        result = format_result('add', 1.23, 4.56, 5.79)
        assert '1.23' in result
        assert '4.56' in result
        assert '5.79' in result

    def test_verification_requirement(self):
        """Test the exact verification requirement from task spec."""
        result = format_result('add', 2, 3, 5)
        assert '2' in result and '3' in result and '5' in result
        print('Formatter import OK')
