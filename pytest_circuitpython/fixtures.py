import pytest
from .utils import get_board


@pytest.fixture(scope='session')
def board(request):
    """
    Return a cpboard.CPboard instance (session scope)
    """
    return get_board(request.session)
