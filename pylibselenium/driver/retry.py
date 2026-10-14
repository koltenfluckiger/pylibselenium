import logging
from functools import partial, wraps
from time import sleep

logger = logging.getLogger(__name__)


def retry(retries=3, delay=1, log=False, backoff=1.0, exceptions=(Exception,)):
    """
    Decorator that retries a function up to ``retries`` times on exception.

    Sleeps ``delay`` seconds between attempts, multiplying the pause by ``backoff`` after every
    failure, and re-raises the last exception once the attempts are exhausted. Only exceptions
    listed in ``exceptions`` trigger a retry; anything else propagates immediately.
    """

    def decorator(func):
        @wraps(func)
        def newfn(*args, **kwargs):
            last_exc = None
            wait = delay
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as err:
                    last_exc = err
                    if attempt < retries - 1:
                        if log:
                            logger.warning(
                                "Retry %s/%s after error: %s; retrying in %ss",
                                attempt + 1,
                                retries,
                                err,
                                wait,
                            )
                        sleep(wait)
                        wait *= backoff
            if last_exc is not None:
                raise last_exc
            return func(*args, **kwargs)

        return newfn

    return decorator


def retry_until_successful(f=None, delay=1, log=False, max_attempts=None):
    """
    Decorator that keeps calling a function until it returns without raising.

    Usable bare (``@retry_until_successful``) or with arguments. ``max_attempts`` bounds the
    number of tries (``None`` means forever, the historical behaviour); the last exception is
    re-raised once the bound is reached.
    """
    if f is None:
        return partial(
            retry_until_successful,
            delay=delay,
            log=log,
            max_attempts=max_attempts,
        )

    @wraps(f)
    def wrapper(*args, **kwargs):
        attempt = 0
        while True:
            try:
                return f(*args, **kwargs)
            except Exception as err:
                attempt += 1
                if max_attempts is not None and attempt >= max_attempts:
                    raise
                if log:
                    logger.warning("Attempt %s failed: %s; retrying in %ss", attempt, err, delay)
                sleep(delay)

    return wrapper
