import logging
from time import sleep
from functools import partial, wraps

def retry(f=None, tries=3, delay=1, log=False):
    if f is None:
        return partial(
            retry,
            delay=delay,
            log=log,
        )
    @wraps(f)
    def wrapper(*args, **kwargs):
        while tries > 0:
            try:
                return f(*args, **kwargs)
            except Exception as err:
                if log:
                    print("Retrying in {}".format(delay))
                tries -= 1
                sleep(delay)
        return f(*args, **kwargs)
    return wrapper

def retry_until_successful(f=None, delay=1, log=False):
    if f is None:
        return partial(
            retry_until_successful,
            delay=delay,
            log=log,
        )
    @wraps(f)
    def wrapper(*args, **kwargs):
        while True:
            try:
                return f(*args, **kwargs)
            except Exception as err:
                if log:
                    print("Retrying in {}".format(delay))
                sleep(delay)
        return f(*args, **kwargs)
    return wrapper
