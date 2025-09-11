try:
    from abc import ABC
    from typing import List
    import os
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()

from selenium.webdriver.chrome.service import Service as CS
from selenium.webdriver.firefox.service import Service as FS
from selenium.webdriver.safari.service import Service as SS


class BrowserService(ABC):

    def factory(self) -> object:
        "Factory function returning service object"


class ChromeService(BrowserService):

    def __init__(
        self, executable_path: str, log_path=f'{os.getenv("TMP")}/chromeservice.log'
    ):
        self.executable_path = executable_path
        self.log_path = log_path

    def factory(self) -> object:
        try:
            return CS(executable_path=self.executable_path, log_path=self.log_path)
        except Exception as err:
            print(err)


class FirefoxService(BrowserService):

    def __init__(
        self, executable_path: str, log_path=f"{os.getenv('TMP')}/firefoxservice.log"
    ):
        self.executable_path = executable_path
        self.log_path = log_path

    def factory(self) -> object:
        try:
            return FS(executable_path=self.executable_path, log_path=self.log_path)
        except Exception as err:
            print(err)


class SafariService(BrowserService):

    def __init__(
        self,
        executable_path: str,
        log_path: str = f"{os.getenv('TMP')}/safariservice.log",
        quiet: bool = False,
    ):
        self.executable_path = executable_path
        self.log_path = log_path
        self.quiet = quiet

    def factory(self) -> object:
        try:
            return SS(
                executable_path=self.executable_path,
                log_path=self.log_path,
                quiet=self.quiet,
            )
        except Exception as err:
            print(err)
