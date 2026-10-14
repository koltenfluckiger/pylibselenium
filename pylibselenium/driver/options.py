"""Browser option wrappers: build a Selenium ``Options`` object from plain Python arguments."""
import logging
from abc import ABC
from typing import Dict, List
from urllib.parse import urlsplit

from selenium.webdriver.chrome.options import Options as ChromeOption
from selenium.webdriver.edge.options import Options as EdgeOption
from selenium.webdriver.firefox.options import Options as FirefoxOption
from selenium.webdriver.safari.options import Options as SafariOption

try:
    from appium.options.common.base import AppiumOptions as _AppiumBaseOptions
except ImportError:  # appium-python-client is only needed for mobile sessions
    _AppiumBaseOptions = None

logger = logging.getLogger(__name__)

# Wrapper-only settings are carried on the raw Selenium options object under these attribute
# names, so the driver factories can read them even when callers pass the raw object (the usual
# ``opts = ChromeOptions(...).factory(); Chrome(service, opts)`` two-step form).
EXTENSIONS_ATTR = "_pylibselenium_extensions"
USER_DATA_DIR_ATTR = "_pylibselenium_user_data_dir"
DOWNLOAD_DIR_ATTR = "_pylibselenium_download_dir"


def _split_proxy(proxy: str) -> tuple[str, int | None]:
    """``host:port`` or ``scheme://host:port`` -> (host, port)."""
    target = proxy if "://" in proxy else f"http://{proxy}"
    parts = urlsplit(target)
    return parts.hostname or proxy, parts.port


class BrowserOptions(ABC):

    def factory(self) -> object:
        """Factory function returning options object"""


class _ChromiumOptions(BrowserOptions):
    """Shared implementation for the Chromium based browsers (Chrome, Edge)."""

    _options_class = ChromeOption
    _logging_prefs_key = "goog:loggingPrefs"

    def __init__(
        self,
        arguments: List[str] = None,
        preferences: Dict = None,
        extension_paths: List[str] = None,
        binary_path: str = None,
        disable_bot_detection_flag: bool = False,
        debug_mode=False,
        headless: bool = False,
        user_agent: str = None,
        proxy: str = None,
        window_size: tuple = None,
        download_dir: str = None,
        page_load_strategy: str = None,
        performance_logging: bool = False,
        user_data_dir: str = None,
        profile_directory: str = None,
    ) -> None:
        """
        Parameters
        ----------
        arguments : list[str], optional
            Raw command line switches (``--disable-notifications``, ...).
        preferences : dict, optional
            Chrome ``prefs`` experimental option.
        extension_paths : list[str], optional
            ``.crx`` files to load.
        binary_path : str, optional
            Browser binary to launch instead of the default installation.
        disable_bot_detection_flag : bool, optional
            Hide the most common automation markers (see ``disable_bot_detection``).
        debug_mode : bool, optional
            Keep the browser open after the driver process exits (``detach``).
        headless : bool, optional
            Run without a window (``--headless=new``).
        user_agent : str, optional
            Override the user agent string.
        proxy : str, optional
            ``host:port`` or ``scheme://host:port`` passed to ``--proxy-server``.
        window_size : tuple[int, int], optional
            Initial window size as ``(width, height)``.
        download_dir : str, optional
            Directory downloads are saved to without prompting.
        page_load_strategy : str, optional
            ``"normal"``, ``"eager"`` or ``"none"``.
        performance_logging : bool, optional
            Enable the ``performance`` log (network/CDP events); off by default because it costs
            CPU and memory on every page. The ``browser`` (console) log is always on.
        user_data_dir : str, optional
            Profile root passed to ``--user-data-dir``; also recorded so ``DriverClient(delete_profile=True)``
            may remove it on quit.
        profile_directory : str, optional
            Profile name inside ``user_data_dir`` (``--profile-directory``).
        """
        self.arguments = list(arguments or [])
        self.preferences = dict(preferences or {})
        self.extension_paths = list(extension_paths or [])
        self.binary_path = binary_path
        self.disable_bot_detection_flag = disable_bot_detection_flag
        self.debug_mode = debug_mode
        self.headless = headless
        self.user_agent = user_agent
        self.proxy = proxy
        self.window_size = window_size
        self.download_dir = download_dir
        self.page_load_strategy = page_load_strategy
        self.performance_logging = performance_logging
        self.user_data_dir = user_data_dir
        self.profile_directory = profile_directory

    def disable_bot_detection(self, options):
        """Remove the obvious automation markers (``navigator.webdriver`` is patched by the client)."""
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return options

    def factory(self) -> object:
        options = self._options_class()
        for arg in self.arguments:
            options.add_argument(arg)
        for ext_path in self.extension_paths:
            options.add_extension(ext_path)
        if self.binary_path:
            options.binary_location = self.binary_path
        if self.headless:
            options.add_argument("--headless=new")
        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")
        if self.window_size:
            width, height = self.window_size
            options.add_argument(f"--window-size={int(width)},{int(height)}")
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
            setattr(options, USER_DATA_DIR_ATTR, str(self.user_data_dir))
        if self.profile_directory:
            options.add_argument(f"--profile-directory={self.profile_directory}")
        if self.page_load_strategy:
            options.page_load_strategy = self.page_load_strategy
        if self.disable_bot_detection_flag:
            options = self.disable_bot_detection(options)
        if self.debug_mode:
            options.add_experimental_option("detach", True)
        logging_prefs = {"browser": "ALL"}
        if self.performance_logging:
            logging_prefs["performance"] = "ALL"
        options.set_capability(self._logging_prefs_key, logging_prefs)
        prefs = dict(self.preferences)
        if self.download_dir:
            prefs.setdefault("download.default_directory", str(self.download_dir))
            prefs.setdefault("download.prompt_for_download", False)
            prefs.setdefault("download.directory_upgrade", True)
            setattr(options, DOWNLOAD_DIR_ATTR, str(self.download_dir))
        options.add_experimental_option("prefs", prefs)
        self.options = options
        return self.options


class ChromeOptions(_ChromiumOptions):

    _options_class = ChromeOption
    _logging_prefs_key = "goog:loggingPrefs"


class EdgeOptions(_ChromiumOptions):

    _options_class = EdgeOption
    _logging_prefs_key = "ms:loggingPrefs"


class FirefoxOptions(BrowserOptions):

    def __init__(
        self,
        arguments: List[str] = None,
        extension_paths: List[str] = None,
        headless: bool = False,
        user_agent: str = None,
        proxy: str = None,
        download_dir: str = None,
        preferences: Dict = None,
        profile_directory: str = None,
        binary_path: str = None,
    ) -> None:
        """
        Parameters
        ----------
        arguments : list[str], optional
            Raw command line switches.
        extension_paths : list[str], optional
            ``.xpi`` files or unpacked extension directories. Selenium 4 installs Firefox add-ons
            after the browser starts, so these are recorded on the options object and installed by
            ``Firefox.factory()``.
        headless, user_agent, proxy, download_dir, preferences, profile_directory, binary_path
            Same meaning as on ``ChromeOptions``; ``preferences`` are ``about:config`` values and
            ``profile_directory`` is an existing profile to copy.
        """
        self.arguments = list(arguments or [])
        self.extension_paths = list(extension_paths or [])
        self.headless = headless
        self.user_agent = user_agent
        self.proxy = proxy
        self.download_dir = download_dir
        self.preferences = dict(preferences or {})
        self.profile_directory = profile_directory
        self.binary_path = binary_path

    def factory(self) -> object:
        options = FirefoxOption()
        for arg in self.arguments:
            options.add_argument(arg)
        if self.headless:
            options.add_argument("-headless")
        if self.binary_path:
            options.binary_location = self.binary_path
        for pref, value in self.preferences.items():
            options.set_preference(pref, value)
        if self.user_agent:
            options.set_preference("general.useragent.override", self.user_agent)
        if self.proxy:
            host, port = _split_proxy(self.proxy)
            options.set_preference("network.proxy.type", 1)
            for scheme in ("http", "ssl"):
                options.set_preference(f"network.proxy.{scheme}", host)
                if port:
                    options.set_preference(f"network.proxy.{scheme}_port", int(port))
        if self.download_dir:
            options.set_preference("browser.download.folderList", 2)
            options.set_preference("browser.download.dir", str(self.download_dir))
            options.set_preference("browser.download.useDownloadDir", True)
            options.set_preference("browser.download.manager.showWhenStarting", False)
            setattr(options, DOWNLOAD_DIR_ATTR, str(self.download_dir))
        if self.profile_directory:
            options.profile = self.profile_directory
        setattr(options, EXTENSIONS_ATTR, list(self.extension_paths))
        self.options = options
        return self.options


class SafariOptions(BrowserOptions):

    def __init__(self, arguments: List[str] = None) -> None:
        self.arguments = list(arguments or [])

    def factory(self) -> object:
        options = SafariOption()
        for arg in self.arguments:
            options.add_argument(arg)
        self.options = options
        return self.options


class AppiumOptions(BrowserOptions):

    def __init__(self, arguments=None, capabilities: Dict = None) -> None:
        """
        Parameters
        ----------
        arguments : dict | list[tuple], optional
            Capabilities as a mapping or ``(name, value)`` pairs (Appium has no command line switches).
        capabilities : dict, optional
            Additional capabilities loaded with ``load_capabilities``.
        """
        self.arguments = arguments or []
        self.capabilities = dict(capabilities or {})

    def factory(self) -> object:
        if _AppiumBaseOptions is None:
            raise ImportError("appium-python-client is required for AppiumOptions")
        options = _AppiumBaseOptions()
        if self.capabilities:
            options.load_capabilities(self.capabilities)
        pairs = self.arguments.items() if isinstance(self.arguments, dict) else self.arguments
        for name, value in pairs:
            options.set_capability(name, value)
        self.options = options
        return self.options
