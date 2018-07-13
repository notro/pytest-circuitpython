# encoding: utf-8
import pytest

# Source: pytest/testing/python/approx.py
# The file has been split in two to avoid memory error
# approx() has been flipped over as left operand
# Some very large values have been scaled down

from pytest import approx


class TestApprox(object):
    def test_operator_overloading(self):
        assert approx(1, rel=1e-6, abs=1e-12) == 1
        assert not (1 != approx(1, rel=1e-6, abs=1e-12))
        assert approx(1, rel=1e-6, abs=1e-12) != 10
        assert not (10 == approx(1, rel=1e-6, abs=1e-12))

    def test_exactly_equal(self):
        # assert pytest.config == 'mock'
        examples = [
            (2.0, 2.0),
            # (0.1e200, 0.1e200),
            (0.1e20, 0.1e20),
            # (1.123e-300, 1.123e-300),
            (1.123e-30, 1.123e-30),
            (12345, 12345.0),
            (0.0, -0.0),
            (345678, 345678),
        ]
        for a, x in examples:
            assert approx(x) == a

    def test_zero_tolerance(self):
        # within_1e10 = [(1.1e-100, 1e-100), (-1.1e-100, -1e-100)]
        within_1e10 = [(1.1e-10, 1e-10), (-1.1e-10, -1e-10)]
        for a, x in within_1e10:
            assert approx(x, rel=0.0, abs=0.0) == x
            assert approx(x, rel=0.0, abs=0.0) != a
            # assert approx(x, rel=0.0, abs=5e-101) == a
            assert approx(x, rel=0.0, abs=5e-11) == a
            # assert approx(x, rel=0.0, abs=5e-102) != a
            assert approx(x, rel=0.0, abs=5e-12) != a
            assert approx(x, rel=5e-1, abs=0.0) == a
            assert approx(x, rel=5e-2, abs=0.0) != a

    def test_negative_tolerance(self):
        # Negative tolerances are not allowed.
        illegal_kwargs = [
            dict(rel=-1e100),
            dict(abs=-1e100),
            dict(rel=1e100, abs=-1e100),
            dict(rel=-1e100, abs=1e100),
            dict(rel=-1e100, abs=-1e100),
        ]
        for kwargs in illegal_kwargs:
            with pytest.raises(ValueError):
                approx(1, **kwargs) == 1.1
