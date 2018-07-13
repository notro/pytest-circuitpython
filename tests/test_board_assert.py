from pytest import raises


def test_board_asserts():
    assert True
    assert not False
    assert 1 == 1
    assert not 1 == 2
    assert 1 is 1
    assert 1 != 2
    assert 1 is not 2
    assert 1 <= 1
    assert 1 <= 2
    assert 2 >= 1
    assert 2 >= 2
    assert 0.99 <= 1.0 <= 1.01
    assert abs((0.1 + 0.2) - 0.3) < 1e-6


def test_board_raises():
    with raises(ZeroDivisionError):
        1 / 0

    with raises(RuntimeError):
        raise NotImplementedError()
