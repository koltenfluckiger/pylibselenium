"""Enumerations shared by the driver client."""
from enum import Enum


class MODIFERKEYS(str, Enum):
    """
    Key codes for modifier and control keys.

    Members are ``str`` subclasses, so they can be passed straight to ``ActionChains.key_down`` or
    ``WebElement.send_keys``; ``.value`` keeps working for callers that already use it.
    """

    CTRL = ""
    ALT = ""
    SHIFT = ""
    ENTER = ""

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


# Correctly spelled alias; ``MODIFERKEYS`` is kept for existing callers.
MODIFIERKEYS = MODIFERKEYS


class DROPDOWNTYPE(Enum):

    INDEX = 1
    VALUE = 2
    TEXT = 3
