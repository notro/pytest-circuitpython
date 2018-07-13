import pytest
import sys
import traceback
import cpboard

if not pytest.config.option.cpboarddev:
    pytest.skip("--cpboard is missing, skipping tests", allow_module_level=True)

@pytest.fixture(scope='session')
def board(request):
    board = cpboard.CPboard.from_try_all(request.config.option.cpboarddev)
    board.open()
    board.repl.reset()
    return board


def test_exec(board):
    board.exec('a = 5')
    board.exec('b = a + 2', reset_repl=False)


test_exec_raises_data = [
    ('a', NameError("name 'a' is not defined")),
    (' a = 0', IndentationError('unexpected indent')),
    ('a(=0', SyntaxError('invalid syntax')),
]

@pytest.mark.parametrize('source, exc', test_exec_raises_data)
def test_exec_raises(board, source, exc):
    with pytest.raises(type(exc)) as excinfo:
        board.exec(source)
    print('excinfo', excinfo, dir(excinfo))
    assert excinfo.value.args == exc.args


test_eval_data = [
    ('3 * 2**3 - 1', 23),
#    ('', ),
]

@pytest.mark.parametrize('expression, result', test_eval_data)
def test_eval(board, expression, result):
    res = board.eval(expression, out=sys.stdout)
    assert res == result


def test_exec_eval(board):
    board.exec('a = 5')
    res = board.eval('a + 2', out=sys.stdout, reset_repl=False)
    assert res == 7


def board_test_exec_func(a, b):
    return a + b

def test_exec_func(board):
    res = board.exec_func(board_test_exec_func, 1, 2, _out=sys.stdout)
    assert res == 3


test_obj_data = [
    None,
    True, False,
    0, 5,
    4.2,
    b'', b"Hello",
    "", "\n", "Hello world",
    """Hello
    world""",
    (), (1,2),
    [], [1,2],
    {}, {'a' : 1, 'b' : 2},
    set(), set([1,2]),
    frozenset(), frozenset([1,2]),
]

@cpboard.remote
def board_test_obj(obj):
    return obj

@pytest.mark.parametrize('obj', test_obj_data)
def test_obj(board, obj):
    import sys
    res = board_test_obj(board, obj, _out=sys.stdout)
    #res = board_test_obj(board, obj)
    assert res == obj


@cpboard.remote
def board_test_namedtuple():
    import collections
    Point = collections.namedtuple('Point', ['x', 'y'])
    return Point(11, y=22)

def test_namedtuple(board):
    import collections
    Point = collections.namedtuple('Point', ['x', 'y'])
    obj = Point(11, y=22)
    res = board_test_namedtuple(board)
    assert obj._asdict() == res._asdict()
    assert type(obj).__name__ == type(res).__name__


test_args_data = [
    ( ( ), { } ),
    ( (1, ), { } ),
    ( (1, 2, ), { } ),
    ( ( ), { 'a' : 3 } ),
    ( ( ), { 'a' : 3, 'b' : 4 } ),
    ( (5, ), { 'a' : 3 } ),
    ( (5, 6, ), { 'a' : 3, 'b' : 4 } ),
    ( ('Hello',), { } ),
    ( ('Hello', ), { 'a' : 'world'} ),
    ( ( ), { 'a' : 'world'} ),
]

@cpboard.remote
def board_test_args(*args, **kwargs):
    return (args, kwargs)

@pytest.mark.parametrize('args, kwargs', test_args_data)
def test_args(board, args, kwargs):
    obj = (args, kwargs)
    res = board_test_args(board, *args, **kwargs)
    assert obj == res


@cpboard.remote
def board_test_exception_missing_argument(arg):
    pass

@cpboard.remote
def board_test_exception_nameerror():
    not_defined

@cpboard.remote
def board_test_exception_oserror():
    raise OSError(110)

test_exception_data = [
    (board_test_exception_missing_argument, TypeError, 'function takes 1 positional arguments but 0 were given'),
    (board_test_exception_nameerror, NameError, 'not_defined'),
    (board_test_exception_oserror, OSError, '110'),
]

@pytest.mark.parametrize('func, exc, val', test_exception_data)
def test_exception(board, func, exc, val):
    with pytest.raises(exc) as excinfo:
        func(board)
    assert val in str(excinfo.value)


@cpboard.remote
def board_test_struct_time(tup):
    import time
    import rtc # make sure we're running on the board
    return time.struct_time(tup)

def test_struct_time(board):
    tup = (2000, 1, 1, 15, 30, 24, 0, 0, 0)
    import time
    obj = time.struct_time(tup)
    res = board_test_struct_time(board, tup)
    assert obj == res

def test_os_uname(board):
    import os
    obj = os.uname()
    res = cpboard.os_uname(board)
    assert type(obj) == type(res)


@cpboard.remote
def board_test_print(obj):
    print(obj.upper())

def test_print(board):
    import io
    out = io.StringIO()
    obj = 'Hello world'
    board_test_print(board, obj, _out=out)
    res = out.getvalue()
    expected = obj.upper()
    assert expected in res



@cpboard.remote
def xtest_assert3(board):
    print(board)
    x = 5
    y = 6
    assert x == y, "%r vs (expected) %r" % (x, y)






@cpboard.remote
def board_test_assert():
    x = 5
    y = 6 - 1
    assert x == y, "%r vs (expected) %r" % (x, y)

#@pytest.mark.skip(reason="try without")
def test_assert(board):
    #import pprint
    #pprint.pprint(sys.modules)
    #mod = sys.modules['pytest_cpboard']
    #print()
    #print(dir(mod))
    board_test_assert(board)


def do_test_assert2():
    assert 5 == 5

def test_assert2():
    do_test_assert2()


# test unicode
