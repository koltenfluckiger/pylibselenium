"""Default browser profile directories per platform."""
import os
from enum import Enum
from pathlib import Path as path

# %APPDATA% already ends in ``\Roaming`` and %LOCALAPPDATA% in ``\Local``; fall back to the
# conventional locations when the variables are not set (e.g. when evaluated on Linux).
_APPDATA = os.getenv("APPDATA") or str(path.home() / "AppData" / "Roaming")
_LOCALAPPDATA = os.getenv("LOCALAPPDATA") or str(path.home() / "AppData" / "Local")


class Directory(Enum):

    DEFAULT_WINDOWS_FIREFOX = "{}\\Mozilla\\Firefox\\Profiles".format(_APPDATA)
    DEFAULT_WINDOWS_CHROME = "{}\\Google\\Chrome\\User Data".format(_LOCALAPPDATA)
    DEFAULT_WINDOWS_EDGE = "{}\\Microsoft\\Edge\\User Data\\Default".format(_LOCALAPPDATA)

    DEFAULT_LINUX_FIREFOX = "{}/.mozilla/firefox/".format(path.home())
    DEFAULT_LINUX_CHROME = "{}/.config/google-chrome/default".format(path.home())
    DEFAULT_LINUX_EDGE = "{}/.config/microsoft-edge".format(path.home())

    def __str__(self):
        return self.value
