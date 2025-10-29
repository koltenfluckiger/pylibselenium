from functools import partial, wraps
from time import sleep

def retry(retries=3, delay=1):
    def decorator(func):
        def newfn(*args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    return func(*args, **kwargs)
                except Exception as err:
                    sleep(delay)
                    attempt += 1
                    return func(*args, **kwargs)
            return func(*args, **kwargs)

        return newfn

    return decorator


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
