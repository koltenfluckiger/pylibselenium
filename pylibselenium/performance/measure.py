import timeit
from functools import wraps


def Measure(f):
    """
    Decorator that times every call of ``f``.

    The duration of the last call, in seconds, is stored on the decorated function as ``.elapsed``
    (``main(); print(main.elapsed)``). The wrapped function's return value is passed through.
    """

    @wraps(f)
    def measured(*args, **kwargs):
        start_time = timeit.default_timer()
        try:
            return f(*args, **kwargs)
        finally:
            measured.elapsed = timeit.default_timer() - start_time

    measured.elapsed = None
    return measured


def MeasureSequence(f):
    """
    Decorator factory: ``@MeasureSequence(setup)`` runs ``setup()`` and then the decorated
    function, timing both together. The total is stored as ``.elapsed`` on the decorated function.
    """

    def wrap(g):
        @wraps(g)
        def timed(*args, **kwargs):
            start_time = timeit.default_timer()
            try:
                f()
                return g(*args, **kwargs)
            finally:
                timed.elapsed = timeit.default_timer() - start_time

        timed.elapsed = None
        return timed

    return wrap
