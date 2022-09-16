try:
    from functools import wraps
    import timeit
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


def Measure(f):
    @wraps(f)
    def time(*args, **kwargs):
        start_time = timeit.default_timer()
        result = f(*args, **kwargs)
        elapsed = timeit.default_timer() - start_time
        time.elapsed = elapsed
        return result
    return time


def MeasureSequence(f):
    def wrap(g):
        @wraps(g)
        def timed():
            start_time = timeit.default_timer()
            f()
            g()
            elapsed = timeit.default_timer() - start_time
            timed.elapsed = elapsed
        return timed
    return wrap
