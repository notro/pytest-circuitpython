import pytest


@pytest.mark.board
def test_mark_board():
    pytest.config == 'mock'


def test_not_mark_board():
    pytest.config != 'mock'
