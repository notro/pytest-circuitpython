"""
pytest: Used by the pytest-circuitpython plugin
"""


class MockDecorator:
    def __call__(self, *args, **kwargs):
        if len(args) and callable(args[0]):
            return args[0]
        else:
            def wrapper(func_):
                return func_
            return wrapper

    def __getattr__(self, attr):
        return MockDecorator()


config = 'config'
fixture = MockDecorator()
mark = MockDecorator()


class ApproxBase(object):
    def __init__(self, expected, rel=None, abs=None, nan_ok=False):
        self.expected = expected
        self.abs = abs
        self.rel = rel
        self.nan_ok = nan_ok


class ApproxScalar(ApproxBase):
    DEFAULT_ABSOLUTE_TOLERANCE = 1e-12
    DEFAULT_RELATIVE_TOLERANCE = 1e-6

    def __repr__(self):
        if isinstance(self.expected, complex):
            return str(self.expected)

        # if math.isinf(self.expected):
        #     return str(self.expected)

        try:
            vetted_tolerance = "{:.1e}".format(self.tolerance)
        except ValueError:
            vetted_tolerance = "???"

        return u"{} \u00b1 {}".format(self.expected, vetted_tolerance)

    def __eq__(self, actual):
        # Short-circuit exact equality.
        if actual == self.expected:
            return True

        print('%r __eq__ %r' % (self.expected, actual))
        print('%r <= %r' % (abs(self.expected - actual), self.tolerance))
        # Return true if the two numbers are within the tolerance.
        return abs(self.expected - actual) <= self.tolerance

    __hash__ = None

    @property
    def tolerance(self):
        def set_default(x, default):
            return x if x is not None else default

        absolute_tolerance = set_default(self.abs, self.DEFAULT_ABSOLUTE_TOLERANCE)

        if absolute_tolerance < 0:
            raise ValueError(
                "absolute tolerance can't be negative: {}".format(absolute_tolerance)
            )
        # if math.isnan(absolute_tolerance):
        #     raise ValueError("absolute tolerance can't be NaN.")

        if self.rel is None:
            if self.abs is not None:
                return absolute_tolerance

        relative_tolerance = set_default(
            self.rel, self.DEFAULT_RELATIVE_TOLERANCE
        ) * abs(self.expected)

        if relative_tolerance < 0:
            raise ValueError(
                "relative tolerance can't be negative: {}".format(absolute_tolerance)
            )
        # if math.isnan(relative_tolerance):
        #     raise ValueError("relative tolerance can't be NaN.")

        return max(relative_tolerance, absolute_tolerance)


def approx(expected, rel=None, abs=None, nan_ok=False):
    cls = ApproxScalar

    return cls(expected, rel, abs, nan_ok)


class OutcomeException(BaseException):
    pass


class Failed(OutcomeException):
    pass


def fail(msg="", pytrace=True):
    raise Failed(msg)


def raises(expected_exception, *args, **kwargs):
    __tracebackhide__ = True
    if not issubclass(expected_exception, BaseException):
        raise TypeError("exceptions must be derived from BaseException, not %s" % type(expected_exception))

    message = "DID NOT RAISE {}".format(expected_exception)
    match_expr = None

    if not args:
        if "message" in kwargs:
            message = kwargs.pop("message")
        if "match" in kwargs:
            match_expr = kwargs.pop("match")
        if kwargs:
            msg = "Unexpected keyword arguments passed to pytest.raises: "
            msg += ", ".join(kwargs.keys())
            raise TypeError(msg)
        return RaisesContext(expected_exception, message, match_expr)
    else:
        raise NotImplementedError()


class RaisesContext(object):
    def __init__(self, expected_exception, message, match_expr):
        self.expected_exception = expected_exception
        self.message = message
        if match_expr:
            raise NotImplementedError('match_expr not supported')
        self.match_expr = match_expr
        self.excinfo = None

    def __enter__(self):
        self.excinfo = 'NotImplemented'
        return self.excinfo

    def __exit__(self, *tp):
        __tracebackhide__ = True
        if tp[0] is None:
            print('self.message', self.message, type(self.message))
            # Keep it simple and use AssertionError for this
            raise AssertionError(self.message)
        print(tp)
        # self.excinfo.__init__(tp)
        suppress_exception = issubclass(tp[0], self.expected_exception)
        # if suppress_exception:
        #     sys.exc_clear()
        # if self.match_expr and suppress_exception:
        #     self.excinfo.match(self.match_expr)
        return suppress_exception
