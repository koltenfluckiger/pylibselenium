try:
    from enum import Enum
    from pathlib import Path as path
    import os
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


class Directory(Enum):

    DEFAULT_WINDOWS_FIREFOX = "{}\\Roaming\\Mozilla\\Firefox\\Profiles".format(
        os.getenv('APPDATA'))
    DEFAULT_WINDOWS_CHROME = "{}\\Local\\Google\\Chrome\\User Data".format(
        os.getenv('APPDATA'))
    DEFAULT_WINDOWS_EDGE = "{}\\Local\\Microsoft\\Edge\\User Data\\Default".format(
        os.getenv('APPDATA'))

    DEFAULT_LINUX_FIREFOX = "{}/.mozilla/firefox/".format(path.home())
    DEFAULT_LINUX_CHROME = "{}/.config/google-chrome/default".format(path.home())
    DEFAULT_LINUX_EDGE = "{}\\Local\\Microsoft\\Edge\\User Data\\Default".format(
        path.home())

    def __str__(self):
        return self.value
