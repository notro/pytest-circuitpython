import cpboard
import pytest


def get_board(session):
    if hasattr(session, 'board'):
        return session.board

    if not session.config.option.boarddev:
        raise pytest.exit('--board has to be set')

    try:
        board = cpboard.CPboard.from_try_all(session.config.option.boarddev)
        board.open()
        board.repl.reset()
    except cpboard.CPboardError as e:
        # FIXME: How is print to console done with pytest?
        print('\nError:', str(e))
        raise session.Interrupted('Failed to access board') from e

    session.board = board
    return session.board
