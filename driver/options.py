try:
    from abc import ABC
    from typing import List, Dict
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()

from selenium.webdriver.chrome.options import Options as ChromeOption
from selenium.webdriver.firefox.options import Options as FirefoxOption
from selenium.webdriver.safari.options import Options as SafariOption


class BrowserOptions(ABC):

    def factory(self) -> object:
        """Factory function returning options object"""


class ChromeOptions(BrowserOptions):

    def __init__(
        self,
        arguments: List[str] = [],
        preferences: Dict = {},
        extension_paths: List[str] = [],
        binary_path: str = None,
        disable_bot_detection_flag: bool = False,
        debug_mode=False,
    ) -> None:
        self.arguments = arguments
        self.preferences = preferences
        self.extension_paths = extension_paths
        self.binary_path = binary_path
        self.disable_bot_detection_flag = disable_bot_detection_flag
        self.debug_mode = debug_mode

    def disable_bot_detection(self, options):
        try:
            options.add_argument("--start-maximized")
            options.add_argument("window-size=1024,768")
            options.add_argument("--disable-blink-features")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            return options
        except Exception as err:
            print(err)

    def factory(self) -> object:
        try:
            options = ChromeOption()
            for arg in self.arguments:
                options.add_argument(arg)
            for ext_path in self.extension_paths:
                options.add_extension(ext_path)
            if self.binary_path:
                options.binary_location = self.binary_path
            if self.disable_bot_detection_flag:
                options = self.disable_bot_detection(options)
            if self.debug_mode:
                options.add_experimental_option("detach", True)
            options.set_capability(
                "goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"}
            )
            options.add_experimental_option("prefs", self.preferences)
            self.options = options
            return self.options
        except Exception as err:
            print(err)


class FirefoxOptions(BrowserOptions):

    def __init__(
        self, arguments: List[str] = [], extension_paths: List[str] = []
    ) -> None:
        self.arguments = arguments
        self.extension_paths = extension_paths

    def factory(self) -> object:
        try:
            options = FirefoxOption()
            for arg in self.arguments:
                options.add_argument(arg)
            for ext_path in self.extension_paths:
                options.add_extension(ext_path)
            self.options = options
            return self.options
        except Exception as err:
            print(err)


class SafariOptions(BrowserOptions):

    def __init__(self, arguments: List[str] = []) -> None:
        self.arguments = arguments

    def factory(self) -> object:
        try:
            options = SafariOption()
            for arg in self.arguments:
                options.add_argument(arg)
            self.options = options
            return self.options
        except Exception as err:
            print(err)
