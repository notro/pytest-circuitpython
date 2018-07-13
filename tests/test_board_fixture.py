import pytest

session_counter = 0
function_counter = 0


@pytest.fixture(scope='session')
def one(request):
    global session_counter
    session_counter += 1
    return 'Session%d' % (session_counter,)


@pytest.fixture
def two(request):
    global function_counter
    function_counter += 1
    return 'Function%d' % (function_counter,)


def test_one_two(one, two):
    assert pytest.config == 'config'
    assert one == 'Session1'
    assert two == 'Function1'


def test_one_two_again(one, two):
    assert one == 'Session1'
    assert two == 'Function2'


three_final = False


@pytest.fixture
def three(request):
    global three_final
    yield 'Three'
    three_final = True


def test_three(three):
    assert three == 'Three'


def test_three_final():
    assert three_final


@pytest.fixture
def four(request):
    return 'Four'


@pytest.fixture
def five(request, four):
    return four + 'Five'


def test_chained_four_five(five):
    assert pytest.config == 'config'
    assert five == 'FourFive'


@pytest.fixture(name='six')
def fixture_six(request):
    return 'Six'


def test_six(six):
    assert pytest.config == 'config'
    assert six == 'Six'
