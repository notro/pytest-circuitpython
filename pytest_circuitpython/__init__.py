# -*- coding: utf-8 -*-

import inspect
import os
import pytest
import re
import sys
import unittest.mock as mock

import cpboard

from .utils import get_board
from .fixtures import *  # noqa: F403,F401


def pytest_addoption(parser):
    group = parser.getgroup('circuitpython')
    group.addoption('--board', dest='boarddev', help='build_name, vid:pid or /dev/tty')
    group.addoption('--file-overwrite', action='store_true', default=False, dest='file_overwrite',
                    help="Force file upload, don't check")


# Import machinery
# https://stackoverflow.com/questions/43571737/how-to-implement-an-import-hook-that-can-modify-the-source-code-on-the-fly-using

_builtins_import = __import__


# https://github.com/posener/mock-import/blob/master/mock_import.py
# https://stackoverflow.com/questions/8658043/how-to-mock-an-import
def try_import(module_name, *args, **kwargs):
    try:
        return _builtins_import(module_name, *args, **kwargs)
    except ImportError:
        return mock.MagicMock()


# Mock missing modules since they are assumed to be present on the board
@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(path, parent):
    config = parent.config
    if not config.option.boarddev:
        return

    if 'test_board_' in str(path):
        debug = config.option.verbose > 1
        with mock.patch('builtins.__import__', try_import):
            mod = path.pyimport(ensuresyspath='prepend')
            if debug:
                print('Import module:', mod.__name__)


def remote_path(session, f):
    rel = os.path.relpath(str(f), str(session.fspath))
    rpath = os.path.join('/tmp.pytest', session.name, rel)
    return rpath


# Mark tests, rewrite assert statements and upload files to the board
@pytest.hookimpl(tryfirst=True)
def pytest_runtestloop(session):
    config = session.config
    if not config.option.boarddev:
        return

    if config.option.collectonly:
        return

    verbose = config.option.verbose

    # print("Session", session, session.fspath)
    # print(dir(session))

    for item in session.items:
        # print('item', item, item.parent)
        # print('  fixturenames', item.fixturenames)
        # print(dir(item), '\n')
        if os.path.basename(item.name).startswith('test_board_') or \
           os.path.basename(item.parent.name).startswith('test_board_') or \
           (item.cls and item.cls.__name__.startswith('TestBoard')):
            item.add_marker('board')

    files = []
    for item in session.items:
        marker = item.get_marker('board')
        if marker is None:
            continue

        item.rpath = remote_path(session, item.fspath)
        path = str(item.fspath)
        if path not in files:
            files.append(path)

    # Access pytest internals to cover all fixtures
    fm = session._fixturemanager
    for argname, fixturedefs in fm._arg2fixturedefs.items():
        if not fixturedefs:
            continue
        for fixturedef in fixturedefs:
            if not fixturedef.baseid:
                continue
            path = os.path.join(str(session.fspath), fixturedef.baseid)
            # print('fixturedef', fixturedef, fixturedef.func, path)
            # print(dir(fixturedef))
            if os.path.basename(path).startswith('test_board_') or fixturedef.func.__name__.startswith('board_'):
                fixturedef.rpath = remote_path(session, path)
                if path not in files:
                    files.append(path)

    if not files:
        return

    board = get_board(session)

    print('\nCopy files to board: ', end='')
    if verbose:
        print()

    disk = cpboard.ReplDisk(board)

    overwrite = config.option.file_overwrite

    def copyfile(src, dst):
        if verbose:
            print('  ', dst, end='')
        else:
            print('.', end='', flush=True)
        disk.makedirs(os.path.dirname(dst), exist_ok=True)
        copied = disk.copy(src, dst, force=overwrite)
        if verbose:
            print('' if copied else ' (unchanged)')

    copyfile(str(os.path.join(os.path.dirname(__file__), 'boardlib', 'pytest.py')), '/lib/pytest.py')

    for f in files:
        src = str(f)
        dst = remote_path(session, f)

        if config.getvalue("assertmode") == "rewrite":
            src = assert_rewrite_module(session, src)

        copyfile(src, dst)

    if not verbose:
        print()


def create_traceback(e, path):
    if not e.exc:
        return False
    path = str(path)
    fname = os.path.basename(path)
    for tb in e.tb:
        # print('tb', tb)
        if fname in tb[0]:
            tb = [(path, tb[1], tb[2])]
            e.exc.__traceback__ = e.create_traceback(tb=tb)
            return True
    return False


def remote_import(session, path):
    debug = session.config.option.verbose > 1
    if debug:
        print('remote_import', path)
    board = session.board

    fname = os.path.basename(path)
    modname = os.path.splitext(fname)[0]

    command = '%r in globals()' % modname
    imported = board.eval(command, reset_repl=False, raise_remote=False)
    if debug:
        print('imported', imported)
    if imported:
        return

    command = 'import os\n'
    command += 'os.chdir(%r)\n' % os.path.dirname(path)
    command += 'import gc; gc.collect()\n'
    if debug:
        command += 'print("Free mem", gc.mem_free())\n'
    command += 'import %s\n' % modname
    if debug:
        command += 'print(globals())\n'
        print('command:\n', command)
    try:
        board.exec(command, reset_repl=False, raise_remote=False, out=sys.stdout)
    except cpboard.CPboardRemoteError as e:
        if debug:
            print('remote_import: e=', e)
        msg = "Failed to import '%s'" % (modname,)
        if e.exc_name:
            msg += '(%s: %s)' % (e.exc_name, e.exc_val)
        raise ImportError(msg) from e


# Import test files on the board
def pytest_runtest_setup(item):
    config = item.config
    if not config.option.boarddev:
        return

    debug = config.option.verbose > 1
    if debug:
        print('pytest_runtest_setup', item)
    marker = item.get_marker('board')
    if marker is None:
        return

    remote_import(item.session, item.rpath)


# Wrap fixture functions and execute them on the board
def pytest_fixture_setup(fixturedef, request):
    if not request.session.config.option.boarddev:
        return

    def fixture_board_wrapper(request, **kwargs):
        __tracebackhide__ = True
        if debug:
            print('fixture_board_wrapper:', request, request)
            print()
        # print(dir(request))
        # print('fixture_board_wrapper: .func', fixture_board_wrapper.func)
        # print('fixture_board_wrapper:', request, dir(request))
        board = request.session.board

        remote_import(request.session, fixturedef.rpath)

        args = [repr('request')]  # dummy value for request argument
        for key in kwargs.keys():
            args.append('%s=fixture_%s_val' % (key, key))

        fname = os.path.basename(fixturedef.rpath)
        modname = os.path.splitext(fname)[0]
        # modname = os.path.splitext(fixturedef.baseid)[0]
        argname = fixturedef.argname
        command = 'res = %s.%s(%s)\n' % (modname, func.__name__, ', '.join(args))
        command += 'fixture_%s = res\n' % (argname,)
        command += 'fixture_%s_val = res\n' % (argname,)

        if debug:
            command += 'print(globals())\n'
            print('command:\n', command)

        try:
            board.exec(command, reset_repl=False, raise_remote=False, out=sys.stdout)
            res = board.eval('res', reset_repl=False, raise_remote=False, strict=False)
        except cpboard.CPboardRemoteError as e:
            if debug:
                print('fixture_board_wrapper: e=', e)
            if e.exc and create_traceback(e, fixturedef.rpath):
                raise e.exc from None
            raise

        if debug:
            print('res: %r' % (res,))

        return res

    def fixture_board_wrapper_yield(request, **kwargs):
        __tracebackhide__ = True
        print('fixture_board_wrapper_yield:', request.function)
        board = request.session.board

        remote_import(request.session, fixturedef.rpath)

        args = [repr('request')]  # dummy value for request argument
        for key in kwargs.keys():
            args.append('%s=fixture_%s_val' % (key, key))

        fname = os.path.basename(fixturedef.rpath)
        modname = os.path.splitext(fname)[0]
        # modname = os.path.splitext(fixturedef.baseid)[0]
        argname = fixturedef.argname
        command = 'fixture_%s = %s.%s(%r)\n' % (argname, modname, func.__name__, ', '.join(args))
        command += 'res = next(fixture_%s)\n' % (argname,)
        command += 'fixture_%s_val = res\n' % (argname,)

        if debug:
            command += 'print(globals())\n'
            print('command:\n', command)

        try:
            board.exec(command, reset_repl=False, raise_remote=False, out=sys.stdout)
            res = board.eval('res', reset_repl=False, raise_remote=False, strict=False)
        except cpboard.CPboardRemoteError as e:
            if debug:
                print('fixture_board_wrapper_yield: e=', e)
            if e.exc and create_traceback(e, fixturedef.rpath):
                raise e.exc from None
            raise

        yield res

        board.exec('next(fixture_%s)' % func.__name__, out=sys.stdout, reset_repl=False, raise_remote=True)

    if not getattr(request.session, 'board', None) or not getattr(fixturedef, 'rpath', ''):
        return

    debug = request.config.option.verbose > 1
    if debug:
        print('pytest_fixture_setup', fixturedef)
        print('fixturedef.func', fixturedef.func)

    # Only wrap the first time called
    if getattr(fixturedef.func, '__wrapped_fixture__', None):
        return

    func = fixturedef.func
    if inspect.isgeneratorfunction(fixturedef.func):
        fixturedef.func = fixture_board_wrapper_yield
    else:
        fixturedef.func = fixture_board_wrapper
    fixturedef.func.__wrapped_fixture__ = func


def delete_variables(board, variables, debug):
    command = ''
    for var in variables:
        command += 'try: del %s\nexcept (NameError, KeyError): pass\n' % (var,)
    command += '__import__("gc").collect()\n'

    if debug:
        command += 'print(globals())\n'
        print('command:\n', command)

    board.exec(command, out=sys.stdout, reset_repl=False, raise_remote=True)


# Clean out fixture variables from the namespace
def pytest_fixture_post_finalizer(fixturedef, request):
    session = request.session
    config = session.config
    if not config.option.boarddev:
        return

    debug = config.option.verbose > 1
    if debug:
        print('\npytest_fixture_post_finalizer:', fixturedef, request)

    func = getattr(fixturedef.func, '__wrapped_fixture__', None)
    if not func:
        return

    argname = fixturedef.argname
    variables = ['fixture_%s' % (argname,), 'fixture_%s_val' % (argname,), 'res']
    delete_variables(session.board, variables, debug)


# Run test functions marked with 'board' on the board
def pytest_pyfunc_call(pyfuncitem):
    config = pyfuncitem.session.config
    if not config.option.boarddev:
        return

    debug = config.option.verbose > 1

    marker = pyfuncitem.get_marker('board')
    if debug:
        print('\n\npytest_pyfunc_call: item:', pyfuncitem, 'parent:', pyfuncitem.parent, 'marker:', marker)

    if marker is None:
        return

    __tracebackhide__ = True
    testfunction = pyfuncitem.obj
    if pyfuncitem._isyieldedfunction():
        # testfunction(*pyfuncitem._args)
        raise NotImplementedError
    else:
        funcargs = pyfuncitem.funcargs
        # testargs = {}
        # for arg in pyfuncitem._fixtureinfo.argnames:
        #     testargs[arg] = funcargs[arg]
        # testfunction(**testargs)

        # print('pytest_pyfunc_call: testargs =', testargs, 'testfunction = ', testfunction)
        # print('pytest_pyfunc_call: pyfuncitem =', pyfuncitem, dir(pyfuncitem))
        # print('pytest_pyfunc_call: pyfuncitem.fixturenames =', pyfuncitem.fixturenames)
        # print('pytest_pyfunc_call: pyfuncitem.funcargs =', pyfuncitem.funcargs)
        # print('pytest_pyfunc_call: pyfuncitem.param =', getattr(pyfuncitem, 'param', "object has no attribute 'param'"))
        # print('pytest_pyfunc_call: board =', pyfuncitem.session.board)

        board = pyfuncitem.session.board

        command = ''

        testargs = []
        for arg in pyfuncitem._fixtureinfo.argnames:
            fixturevar = 'fixture_%s_val' % (arg,)
            argvar = 'funcarg_%s_val' % (arg,)
            # If this is not a remote fixture argument, use the passed in argument value
            command += 'try: %s = %s\nexcept (NameError, KeyError): %s = %r\n' % (argvar, fixturevar, argvar, funcargs[arg])
            testargs.append('%s=%s' % (arg, argvar))
            # testargs.append('%s=%r' % (arg, funcargs[arg]))

        fname = os.path.basename(pyfuncitem.rpath)
        modname = os.path.splitext(fname)[0]

        if pyfuncitem.cls:
            name = pyfuncitem.cls.__name__
            varname = 'test_class_%s' % (name,)
            # Instantiate the test class if it's not already done
            command += 'try: %s\nexcept (NameError, KeyError): %s = %s.%s()\n' % (varname, varname, modname, name)
            command += varname
        else:
            command += modname

        command += '.%s(%s)\n' % (testfunction.__name__, ', '.join(testargs))

        # command  = '%s.%s(%s)\n' % (modname, testfunction.__name__, ', '.join(testargs))

        if debug:
            command += 'print(globals())\n'
            print('command:\n', command)

        try:
            board.exec(command, reset_repl=False, raise_remote=False, out=sys.stdout)
        except cpboard.CPboardRemoteError as e:
            if debug:
                print('pytest_pyfunc_call: e=', e)
            if e.exc:
                for tb in e.tb:
                    if fname in tb[0]:
                        tb = [(str(pyfuncitem.fspath), tb[1], tb[2])]
                        if debug:
                            print('tb', tb)
                        e.exc.__traceback__ = e.create_traceback(tb=tb)
                        raise e.exc from None
            raise

    return True


# Clean out funcarg variables from the namespace
def pytest_runtest_teardown(item, nextitem):
    config = item.config
    if not config.option.boarddev:
        return

    debug = config.option.verbose > 1
    if debug:
        print('\n\npytest_runtest_teardown: item =', item, item.parent)

    marker = item.get_marker('board')
    if marker is None:
        return

    try:
        argnames = item._fixtureinfo.argnames
    except Exception:
        return

    variables = ['funcarg_%s_val' % (arg,) for arg in argnames]
    delete_variables(item.session.board, variables, debug)


def assert_rewrite_module(session, fname):
    debug = session.config.option.verbose > 2
    with open(fname) as f:
        source = f.read()

    s = []
    changed = False
    for line in source.splitlines():
        if re.match(r'\s+assert\s+', line):
            org = line
            line = assert_rewrite(line, debug)
            if line != org:
                changed = True
        s.append(line)

    if not changed:
        return fname

    rewrite = '\n'.join(s)
    if debug:
        print('\nassert_rewrite_module(%r)' % fname)
        print('--------------------------------------------------------------------------------')
        print(rewrite)
        print('--------------------------------------------------------------------------------')

    cache_dir = os.path.join(str(session.fspath), ".pytest_board_cache")
    rel = os.path.relpath(fname, str(session.fspath))
    dst = os.path.join(cache_dir, rel)
    if debug:
        print('dst', dst)

    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
    except OSError:
        return fname

    with open(dst, 'w') as f:
        f.write(rewrite)

    return dst


import token, symbol, parser


def assert_rewrite(line, debug):
    org_line = line
    map = dict(token.tok_name)
    map.update(symbol.sym_name)

    # https://stackoverflow.com/a/5454348
    def shallow(ast):
        if not isinstance(ast, list):
            return ast
        if len(ast) == 2:
            return shallow(ast[1])
        return [map[ast[0]]] + [shallow(a) for a in ast[1:]]

    try:
        ast = shallow(parser.st2list(parser.suite(line.strip())))
    except SyntaxError as e:
        if debug:
            print('assert_rewrite: Parsing error', e)
        return org_line

    if debug:
        print('XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX', line)
        import pprint
        pprint.pprint(ast)

    try:
        if ast[0] != 'file_input' or ast[1][0] != 'simple_stmt' or ast[1][1][0] != 'assert_stmt':
            return org_line
        simple_stmt = ast[1]
        comment = simple_stmt[2]
        assert_stmt = ast[1][1]
        expression = assert_stmt[2]
    except IndexError:
        return org_line

    if len(assert_stmt) > 3:  # Already has a message
        return org_line

    if debug:
        print('comment', comment)
    if comment:
        line = line[:line.index(comment)].rstrip()
        if debug:
            print('new line: %r' % line)

    if debug:
        print('assert_stmt', len(assert_stmt), assert_stmt)
        print('expression', expression)

    ws, assrt, rest = line.partition('assert')

    if not isinstance(expression, list):
        rewrite = ws + '____l = ' + expression + '; assert ____l, "%r" % ____l'
        return rewrite

    # TODO: expression ['not_test', 'not', 'False']
    #       expression ['not_test', 'not', ['comparison', '1', '==', '2']]
    if len(expression) < 4 or expression[0] != 'comparison':
        return org_line

    # TODO: expression ['comparison', '1', '<=', '1', '<=', '1']
    if len(expression) > 4:
        return org_line

    op = expression[2]
    if debug:
        print('left', expression[1])
        print('op', op)
        print('right', expression[3])

    # TODO: op ['comp_op', 'is', 'not']
    if isinstance(op, list):
        return org_line

    # In case of mutiple op's in the line, find the correct one to split on

    def flatten(lst):
        for e in lst:
            if isinstance(e, list):
                yield from flatten(e)
            else:
                yield e

    num_ops = list(flatten([expression[1]])).count(op)
    if debug:
        print('num_ops', num_ops)
        print('rest', rest)

    index = -1
    for num in range(num_ops + 1):
        index = rest.find(op, index + 1)
        if debug:
            print('index', index)
        if index == -1:
            return org_line

    left = rest[:index].strip()
    right = rest[index + len(op):].strip()
    if debug:
        print('left: %r' % left)
        print('right: %r' % right)

    rewrite = ws + '____l = ' + left + '; ____r = ' + right + '; assert ____l ' + op + ' ____r, "%r ' + op + ' %r" % (____l, ____r)'
    if debug:
        print('rewrite', rewrite)

    return rewrite
