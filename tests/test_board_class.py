import pytest


class TestBoardClass:
    def test_one(self):
        assert pytest.config == 'config'
        self.t = 1

    def test_two(self):
        assert pytest.config == 'config'
        assert self.t == 1
