import pytest


@pytest.mark.parametrize("test_input,expected", [
    ("3+5", 8),
    ("2+4", 6),
    ("6*9", 54),
])
def test_eval(test_input, expected):
    assert pytest.config == 'config'
    assert eval(test_input) == expected


test_eval_data = [
    ('3 * 2**3 - 1', 23),
]


@pytest.mark.parametrize('expression, result', test_eval_data)
def test_eval2(expression, result):
    assert pytest.config == 'config'
    assert eval(expression) == result
