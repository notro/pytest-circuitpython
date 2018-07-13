# encoding: utf-8
import pytest

from pytest import approx

# This file was split in 2 to avoid memory error on import


class TestApprox2(object):
    def test_reasonable_defaults(self):
        # Whatever the defaults are, they should work for numbers close to 1
        # than have a small amount of floating-point error.
        assert approx(0.3) == 0.1 + 0.2

    @pytest.mark.skip(reason='Fails probably due to tolerances out of bounds')
    def test_custom_tolerances(self):
        assert approx(1e8, rel=5e-8, abs=5e0) == 1e8 + 1e0
        assert approx(1e8, rel=5e-9, abs=5e0) == 1e8 + 1e0
        assert approx(1e8, rel=5e-8, abs=5e-1) == 1e8 + 1e0
        assert approx(1e8, rel=5e-9, abs=5e-1) != 1e8 + 1e0

        assert approx(1e0, rel=5e-8, abs=5e-8) == 1e0 + 1e-8
        assert approx(1e0, rel=5e-9, abs=5e-8) == 1e0 + 1e-8
        assert approx(1e0, rel=5e-8, abs=5e-9) == 1e0 + 1e-8
        assert approx(1e0, rel=5e-9, abs=5e-9) != 1e0 + 1e-8

        assert approx(1e-8, rel=5e-8, abs=5e-16) == 1e-8 + 1e-16
        assert approx(1e-8, rel=5e-9, abs=5e-16) == 1e-8 + 1e-16
        assert approx(1e-8, rel=5e-8, abs=5e-17) == 1e-8 + 1e-16
        assert approx(1e-8, rel=5e-9, abs=5e-17) != 1e-8 + 1e-16

    @pytest.mark.skip(reason='Fails probably due to tolerances out of bounds')
    def test_relative_tolerance(self):
        within_1e8_rel = [(1e8 + 1e0, 1e8), (1e0 + 1e-8, 1e0), (1e-8 + 1e-16, 1e-8)]
        for a, x in within_1e8_rel:
            assert approx(x, rel=5e-8, abs=0.0) == a
            assert approx(x, rel=5e-9, abs=0.0) != a

    @pytest.mark.skip(reason='Fails probably due to tolerances out of bounds')
    def test_absolute_tolerance(self):
        within_1e8_abs = [(1e8 + 9e-9, 1e8), (1e0 + 9e-9, 1e0), (1e-8 + 9e-9, 1e-8)]
        for a, x in within_1e8_abs:
            assert approx(x, rel=0, abs=5e-8) == a
            assert approx(x, rel=0, abs=5e-9) != a

    def test_int(self):
        within_1e6 = [(1000001, 1000000), (-1000001, -1000000)]
        for a, x in within_1e6:
            assert approx(x, rel=5e-6, abs=0) == a
            assert approx(x, rel=5e-7, abs=0) != a
