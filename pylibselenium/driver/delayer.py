"""Helpers that pace method calls with a fixed delay."""
import logging
import time
from functools import wraps
from types import FunctionType

logger = logging.getLogger(__name__)

_DEFAULT_IGNORE = ("__init__", "__del__", "_kill_processes", "_delete_profile", "check_throw")


def DelayerMetaClass(function, timer, ignore=None):
    """
    Build a metaclass that wraps every plain function of a class with ``function(attribute, timer)``.

    ``ignore`` is an iterable (or dict) of attribute names that must not be wrapped; it defaults to
    the client's lifecycle and error-handling methods.
    """
    ignore = set(_DEFAULT_IGNORE if ignore is None else ignore)

    class MetaClass(type):
        def __new__(cls, classname, bases, classDict):
            newClassDict = {}
            for attributeName, attribute in classDict.items():
                if isinstance(attribute, FunctionType) and attribute.__name__ not in ignore:
                    attribute = function(attribute, timer)
                newClassDict[attributeName] = attribute
            return type.__new__(cls, classname, bases, newClassDict)

    return MetaClass


def delayed_function(func, timer):
    """Return ``func`` wrapped so that every call first sleeps ``timer`` seconds."""

    @wraps(func)
    def wrapped(*args, **kwargs):
        logger.debug("Delaying %s for %ss", getattr(func, "__name__", func), timer)
        time.sleep(timer)
        return func(*args, **kwargs)

    return wrapped
