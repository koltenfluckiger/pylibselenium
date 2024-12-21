from types import FunctionType
import time


def DelayerMetaClass(
    function,
    timer,
    ignore={
        "__init__": "",
        "__del__": "",
        "_kill_processes": "",
        "_delete_profile": "",
        "check_throw": "",
    },
):

    class MetaClass(type):
        def __new__(cls, classname, bases, classDict):
            newClassDict = {}
            for attributeName, attribute in classDict.items():
                if type(attribute) == FunctionType:
                    if attribute.__name__ not in ignore:
                        attribute = function(attribute, timer)
                newClassDict[attributeName] = attribute
            return type.__new__(cls, classname, bases, newClassDict)

    return MetaClass


def delayed_function(func, timer):
    def wrapped(*args, **kwargs):
        print(f"Delaying for.... {timer}")
        time.sleep(timer)
        return func(*args, **kwargs)

    return wrapped
