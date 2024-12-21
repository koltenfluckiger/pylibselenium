try:
    from enum import Enum
    from selenium.webdriver.common.keys import Keys
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


class MODIFERKEYS(Enum):

    CTRL = "\ue009"
    ALT = "\ue00a"
    SHIFT = "\ue008"
    ENTER = "\ue007"

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


class DROPDOWNTYPE(Enum):

    INDEX = 1
    VALUE = 2
    TEXT = 3
