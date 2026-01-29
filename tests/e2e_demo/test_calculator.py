"""Unit tests for calculator module."""

import pytest
from tests.e2e_demo.calculator import add, subtract


class TestAdd:
    """Test suite for add() function."""

    def test_add_positive_integers(self):
        """Test adding two positive integers."""
        assert add(2, 3) == 5
        assert add(10, 20) == 30

    def test_add_negative_integers(self):
        """Test adding negative integers."""
        assert add(-5, -3) == -8
        assert add(-10, 5) == -5
        assert add(10, -5) == 5

    def test_add_floats(self):
        """Test adding floating point numbers."""
        assert pytest.approx(add(2.5, 3.7)) == 6.2
        assert pytest.approx(add(1.1, 2.2)) == 3.3

    def test_add_with_zero(self):
        """Test adding zero."""
        assert add(5, 0) == 5
        assert add(0, 5) == 5
        assert add(0, 0) == 0

    def test_add_large_numbers(self):
        """Test adding large numbers."""
        assert add(1000000, 2000000) == 3000000
        assert add(999999, 1) == 1000000


class TestSubtract:
    """Test suite for subtract() function."""

    def test_subtract_positive_integers(self):
        """Test subtracting positive integers."""
        assert subtract(5, 2) == 3
        assert subtract(10, 3) == 7

    def test_subtract_negative_integers(self):
        """Test subtracting negative integers."""
        assert subtract(-5, -3) == -2
        assert subtract(-10, 5) == -15
        assert subtract(10, -5) == 15

    def test_subtract_floats(self):
        """Test subtracting floating point numbers."""
        assert pytest.approx(subtract(10.5, 3.2)) == 7.3
        assert pytest.approx(subtract(5.5, 2.3)) == 3.2

    def test_subtract_with_zero(self):
        """Test subtracting zero."""
        assert subtract(5, 0) == 5
        assert subtract(0, 5) == -5
        assert subtract(0, 0) == 0

    def test_subtract_same_numbers(self):
        """Test subtracting a number from itself."""
        assert subtract(5, 5) == 0
        assert subtract(100, 100) == 0

    def test_subtract_large_numbers(self):
        """Test subtracting large numbers."""
        assert subtract(2000000, 1000000) == 1000000
        assert subtract(1000000, 999999) == 1


class TestCombined:
    """Test suite for combined operations."""

    def test_add_then_subtract(self):
        """Test combining add and subtract operations."""
        result = add(10, 5)
        assert subtract(result, 3) == 12

    def test_subtract_then_add(self):
        """Test combining subtract and add operations."""
        result = subtract(10, 3)
        assert add(result, 5) == 12

    def test_properties(self):
        """Test mathematical properties."""
        # Commutative property of addition
        assert add(3, 5) == add(5, 3)

        # Subtraction is not commutative
        assert subtract(5, 3) != subtract(3, 5)

        # Adding and subtracting same value
        assert subtract(add(10, 5), 5) == 10
