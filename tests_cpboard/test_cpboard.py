import pytest
import sys
import traceback
sys.path.append('/home/pi')
import cpboard

import os
import os.path
import usb.core


def test_new(monkeypatch):
    device = '/dev/tty0'
    board = cpboard.CPboard(device)
    assert board.device == device

    name = 'really_unknown'
    with pytest.raises(ValueError) as excinfo:
        cpboard.CPboard.from_build_name(name)
    assert name in str(excinfo.value)

    with pytest.raises(RuntimeError):
        cpboard.CPboard.from_usb(idVendor=0xdead, idProduct=0xbeef)

    class Device:
        def __init__(self):
            self.port_numbers = [91, 19]

    def find(*args, **kwargs):
        return Device()

    def listdir(path):
        return ['pre:91.19:post']

    def realpath(path):
        return '/dev/tty9119'

    monkeypatch.setattr(usb.core, 'find', find)
    monkeypatch.setattr(os, 'listdir', listdir)
    monkeypatch.setattr(os.path, 'realpath', realpath)
    device = realpath('')

    board = cpboard.CPboard.from_usb(idVendor=0xabcd, idProduct=0xdcba)
    assert board.device == device

    board = cpboard.CPboard.from_build_name('feather_m0_express')
    assert board.device == device

    board = cpboard.CPboard.from_try_all('feather_m0_express')
    assert board.device == device


test_parse_traceback_data = [
    (b'Traceback (most recent call last):\r\n  File "<stdin>", line 6, in <module>\r\n  File "<stdin>", line 4, in test_remote\r\nAssertionError: 11 vs (expected) 6\r\n',
         AssertionError, '11 vs (expected) 6',
         [ ('<stdin>', 6, '<module>'), ('<stdin>', 4, 'test_remote'), ] ),
    (b'Traceback (most recent call last):\r\n  File "<stdin>", line 1, in <module>\r\n  File "test_unittest.py", line 4, in test\r\n  File "unittest.py", line 9, in assertEqual\r\nAssertionError: 0 vs (expected) 1\r\n',
         AssertionError, '0 vs (expected) 1',
         [ ('<stdin>', 1, '<module>'), ('test_unittest.py', 4, 'test'), ('unittest.py', 9, 'assertEqual'), ] ),
    (b'Traceback (most recent call last):\r\n  File "<stdin>", line 1, in <module>\r\n  File "<string>", line 1, in <module>\r\nTypeError: time.struct_time() takes exactly 1 argument\r\n',
         TypeError, 'time.struct_time() takes exactly 1 argument',
         [ ('<stdin>', 1, '<module>'), ('<string>', 1, '<module>'), ] ),
    (b'Traceback (most recent call last):\r\n  File "<stdin>", line 3\r\nIndentationError: unexpected indent\r\n',
         IndentationError, 'unexpected indent',
         [ ('<stdin>', 3, None), ]),
]

@pytest.mark.parametrize('error, exc_type, exc_val, tb', test_parse_traceback_data)
def test_parse_traceback(error, exc_type, exc_val, tb):
    exc = cpboard.CPboardRemoteError(error)
    assert exc.error == error
    assert type(exc.exc) == exc_type
    assert exc_val in str(exc.exc)
    assert exc.tb == tb


def _create_traceback_func():
    a = 5
    b = 6
    assert a == b, '%r != %r' % (a, b)
    indent = 0

test_create_traceback_data = [
    ('AssertionError: 5 != 6', 4, "assert a == b, '%r != %r' % (a, b)"),
    ('IndentationError: unexpected indent', 5, 'indent = 0'),
]

@pytest.mark.parametrize('exc_str, lineno, check', test_create_traceback_data)
def test_create_traceback(exc_str, lineno, check):
    func = _create_traceback_func
    error = 'Traceback (most recent call last):\r\n  File "<stdin>", line 1, in <module>\r\n  File "test_cpboard.py", line %d, in _create_traceback_func\r\n%s\r\n' % (lineno, exc_str)
    error = error.encode('ascii')
    exc = cpboard.CPboardRemoteError(error)
    exc.__traceback__ = exc.create_traceback(func=func)
    #raise exc
    try:
        raise exc
    except cpboard.CPboardRemoteError as e:
        tb_str = traceback.format_exc()
    firstlineno = func.__code__.co_firstlineno
    line = 'File "test_cpboard.py", line %d, in _create_traceback_func' % (firstlineno + lineno - 1)
    assert line in tb_str
    assert check in tb_str
    #print(tb_str); assert 0
