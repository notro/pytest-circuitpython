====================
pytest-circuitpython
====================


The ```pytest-circuitpython``` `pytest`_ plugin makes it easy to run tests on a CircuitPython board.

Note:
This is a very early release. It is yet to be used outside running it's own tests.

Initial discussion happens here: adafruit/circuitpython#980

----

This plugin uploads and runs tests on a CircuitPython board through it's serial REPL.

The following rules decide if a test or fixture is run on the board:

* If the file name starts with ```test_board_`` all it's tests and fixtures are run on the board.

* If a test starts with ``test_board_`` or is marked with ``@pytest.mark.board`` it runs on the board.

* If a fixture starts with ```board_``` it is run on the board. pytest does not support ```@pytest.mark``` on fixtures.

  Use the ```name``` parameter if you don't want ```board_``` in the fixture name:

    .. code-block:: python

        @pytest.fixture(name='d0')
        def board_d0(request):
            import board
            return board.D0

        def test_d0(d0):
            assert d0 == 'board.D0'


There is some `assert <https://docs.pytest.org/en/latest/assert.html>`_ rewriting before uploading the test file.
It happens on the source code and is much simpler than what pytest does with the AST_.
Chained comparison operators and ```is not``` are not supported (yet):

.. code-block:: python

    assert 1 is not 2
    assert 0.99 <= 1.0 <= 1.01

The code still contains a lot of debug stuff. Debug output can be enable with ``-vv`` and ``-vvv``.
Some of this will probably be put under ``--debug`` later.

See the tests directory for example tests.


Test file upload
----------------

Files are currently being uploaded through the REPL and not via the USB drive.
This means that the filesystem has to be remounted writeable (from the board perspective).

Example boot.py:

.. code-block:: python

    import board
    import digitalio
    import storage

    switch = digitalio.DigitalInOut(board.A4)
    switch.direction = digitalio.Direction.INPUT
    switch.pull = digitalio.Pull.UP

    # If the A4 pin is connected to ground CircuitPython can write to the drive
    storage.remount("/", switch.value)

Ref: https://learn.adafruit.com/circuitpython-essentials/circuitpython-storage

The reason for using the REPL to copy files is to avoid complexity with multiple connected boards and USB auto-mounting coupled with possible board resets.
This might change if USB drive access can be made robust.


cpboard.py
----------

This plugin relies on cpboard.py (included) for communication with the board. It is an expanded version of the one that's in the CircuitPython repo: `tools/cpboard.py`_.

It remains to be seen if cpboard.py will be part of this plugin or a separate package.


Requirements
------------

* Python 3.4 or greater

* pytest 3.5.0 or greater

* Linux (not tested on MacOS or Windows).
  Long term goal is to support all three which should be possible since all communication happens through pyserial_.


Installation
------------

You can install "pytest-circuitpython" from Github:

.. code-block:: shell

    $ pip install git+https://github.com/notro/pytest-circuitpython


Usage
-----

Specify which board to run the tests on:

.. code-block:: shell

    $ pytest --board=feather_m0_express

The board serial device can be specified either as the CircuitPython build name, USB VID:PID or the tty:

.. code-block:: shell

    $ pytest -h

    circuitpython:
      --board=BOARDDEV      build_name, vid:pid or /dev/tty
      --file-overwrite      Force file upload, don't check

This plugin does nothing if the ``--board`` argument is missing.


Limitations
-----------

* Fixtures in conftest.py can not currently run on the board. The file isn't uploaded.

* Parameterized fixtures are not supported.

* The request argument to board fixtures has a dummy value.

* `pytest.approx`_ can only be the left operand. See CircuitPython issue `#1001`_.

* There is a simple pickle/unpickle protocol used (mainly repr()), so it limits which objects can be exchanged between tests/fixtures on the board and locally.

* Exceptions on the board are re-raised locally with a custom traceback pointing to the test file.
  This seems to work for tests but not fixtures, it needs more attention.

* If a test file changes but the file length stays the same, it is not uploaded to the board.
  Some checksumming is needed to improve on this. hashlib_ would probably have helped if it was included in the build.

* Namespace cleanup needs improvement by removing more test variables during run to avoid running out of memory.
At least classes and modules are missing cleanup (pytest_fixture_post_finalizer(), pytest_runtest_teardown()).


Testing
-------

tox can be used for testing::

    $ tox -- --cpboard=feather_m0_express tests_cpboard/
    $ tox -- --board=feather_m0_express tests/


Contributing
------------
Contributions are very welcome.


License
-------

Distributed under the terms of the `MIT`_ license, "pytest-circuitpython" is free and open source software


Issues
------

If you encounter any problems, please `file an issue`_ along with a detailed description.

----

This `pytest`_ plugin was generated with `Cookiecutter`_ along with `@hackebrot`_'s `cookiecutter-pytest-plugin`_ template.

.. _`Cookiecutter`: https://github.com/audreyr/cookiecutter
.. _`@hackebrot`: https://github.com/hackebrot
.. _`MIT`: http://opensource.org/licenses/MIT
.. _`cookiecutter-pytest-plugin`: https://github.com/pytest-dev/cookiecutter-pytest-plugin
.. _`file an issue`: https://github.com/notro/pytest-circuitpython/issues
.. _`pytest`: https://github.com/pytest-dev/pytest
.. _`tox`: https://tox.readthedocs.io/en/latest/
.. _`pip`: https://pypi.org/project/pip/
.. _`PyPI`: https://pypi.org/project
.. _`pytest.approx`: https://docs.pytest.org/en/latest/reference.html#pytest-approx
.. _hashlib: https://circuitpython.readthedocs.io/en/latest/docs/library/hashlib.html
.. _pyserial: https://pyserial.readthedocs.io/en/latest/
.. _`tools/cpboard.py`: https://github.com/adafruit/circuitpython/blob/master/tools/cpboard.py
.. _`#1001`: https://github.com/adafruit/circuitpython/issues/1001
.. _AST: https://en.wikipedia.org/wiki/Abstract_syntax_tree
