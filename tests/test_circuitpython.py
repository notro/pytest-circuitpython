# -*- coding: utf-8 -*-


def test_help_message(testdir):
    result = testdir.runpytest(
        '--help',
    )
    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        'circuitpython:',
        '*--board=BOARDDEV*',
    ])


def test_fixture_board_boarddev_not_set(testdir):
    testdir.makepyfile("""
        import pytest

        def test_fixture_board(board):
            print(board)
            assert board
    """)

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*Exit: --board has to be set*',
    ])

    assert result.ret == 2


def test_fixture_board_boarddev_wrong(testdir):
    testdir.makepyfile("""
        import pytest

        def test_fixture_board(board):
            print(board)
            assert board
    """)

    result = testdir.runpytest('-v', '--board=noexist')

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*Interrupted: Failed to access board*',
    ])

    assert result.ret == 2


def xtest_hello_ini_setting(testdir):
    testdir.makeini("""
        [pytest]
        HELLO = world
    """)

    testdir.makepyfile("""
        import pytest

        @pytest.fixture
        def hello(request):
            return request.config.getini('HELLO')

        def test_hello_world(hello):
            assert hello == 'world'
    """)

    result = testdir.runpytest('-v')

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*::test_hello_world PASSED*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0
