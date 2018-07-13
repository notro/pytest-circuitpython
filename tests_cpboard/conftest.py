import pytest

def pytest_addoption(parser):
    group = parser.getgroup('cpboard')
    group.addoption("--cpboard", dest='cpboarddev', help='build_name, vid:pid or /dev/tty')

def pytest_cmdline_main(config):
    if config.option.boarddev:
        raise pytest.UsageError('Use --cpboard for these tests, not --board')
