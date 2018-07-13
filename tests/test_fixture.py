import pytest


@pytest.fixture(name='d0')
def board_d0(request):
    assert request == 'request'
    import board
    return board.D0


def test_d0(d0):
    assert pytest.config != 'config'
    assert d0 == 'board.D0'


def test_board_d0(d0):
    assert pytest.config == 'config'
    import board
    assert d0 == board.D0


@pytest.fixture
def number(request):
    assert request != 'request'
    return 7845


def test_number(number):
    assert pytest.config != 'config'
    assert number == 7845


def test_board_number(number):
    assert pytest.config == 'config'
    assert number == 7845
