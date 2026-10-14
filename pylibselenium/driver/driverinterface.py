"""Driver factories: build a Selenium WebDriver from a service and options (wrapper or raw)."""
import logging
from abc import ABC

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptionRaw
from selenium.webdriver.chrome.service import Service as ChromeServiceRaw
from selenium.webdriver.edge.service import Service as EdgeServiceRaw
from selenium.webdriver.firefox.options import Options as FirefoxOptionRaw
from selenium.webdriver.firefox.service import Service as FirefoxServiceRaw
from selenium.webdriver.safari.service import Service as SafariServiceRaw

from .options import EXTENSIONS_ATTR, BrowserOptions
from .preferences import FirefoxPreferences
from .services import BrowserService, _usable_executable

try:
    from appium import webdriver as appium_webdriver
except ImportError:  # appium-python-client is only needed for mobile sessions
    appium_webdriver = None

logger = logging.getLogger(__name__)


def _unwrap(obj):
    """Call ``.factory()`` on a pylibselenium wrapper; pass raw Selenium objects (or None) through."""
    if isinstance(obj, (BrowserOptions, BrowserService, FirefoxPreferences)):
        return obj.factory()
    return obj


def normalize_grid_url(url: str) -> str:
    """Add ``http://`` when the scheme is missing and strip trailing slashes."""
    url = (url or "").strip()
    if not url:
        raise ValueError("A Selenium Grid / remote WebDriver URL is required")
    if "://" not in url:
        url = "http://" + url
    return url.rstrip("/")


class DriverInterface(ABC):
    def factory(self) -> object:
        """Factory function returns driver object"""


class _LocalDriver(DriverInterface):
    """Shared start-up for browsers driven through a local driver process."""

    _service_class = None
    _driver_class = None

    def __init__(self, service=None, options=None, *, executable_path: str = None) -> None:
        self.service = service
        self.options = options
        self.executable_path = executable_path

    def _build_service(self):
        service = _unwrap(self.service)
        if service is None:
            path = _usable_executable(self.executable_path)
            if path:
                service = self._service_class(executable_path=path)
        return service

    def _build_options(self):
        return _unwrap(self.options)

    def _start(self, options, service):
        kwargs = {"options": options}
        if service is not None:
            kwargs["service"] = service
        return self._driver_class(**kwargs)

    def factory(self) -> object:
        """Start the browser. Raises (after logging) when the driver cannot be started."""
        try:
            return self._start(self._build_options(), self._build_service())
        except Exception:
            logger.exception("Failed to start %s", self._driver_class.__name__)
            raise


class Chrome(_LocalDriver):

    _service_class = ChromeServiceRaw
    _driver_class = webdriver.Chrome

    def __init__(
        self,
        service: BrowserService = None,
        options: BrowserOptions = None,
        *,
        executable_path: str = None,
        chrome_options: BrowserOptions = None,
    ) -> None:
        """
        Parameters
        ----------
        service : ChromeService | selenium Service, optional
            Driver service; ``None`` lets Selenium Manager pick a matching chromedriver.
        options : ChromeOptions | selenium Options, optional
            Wrapper or raw options.
        executable_path : str, optional
            Legacy: path to chromedriver, used only when it exists and no service is given.
        chrome_options : ChromeOptions | selenium Options, optional
            Legacy alias of ``options``.
        """
        super().__init__(
            service, options if options is not None else chrome_options, executable_path=executable_path
        )


class Edge(_LocalDriver):

    _service_class = EdgeServiceRaw
    _driver_class = webdriver.Edge

    def __init__(
        self,
        service: BrowserService = None,
        options: BrowserOptions = None,
        *,
        executable_path: str = None,
    ) -> None:
        super().__init__(service, options, executable_path=executable_path)


class Firefox(_LocalDriver):

    _service_class = FirefoxServiceRaw
    _driver_class = webdriver.Firefox

    def __init__(
        self,
        service: BrowserService = None,
        options: BrowserOptions = None,
        *,
        executable_path: str = None,
        firefox_options: BrowserOptions = None,
        firefox_profile=None,
    ) -> None:
        """
        Parameters
        ----------
        service, options, executable_path
            As for ``Chrome``.
        firefox_options : FirefoxOptions | selenium Options, optional
            Legacy alias of ``options``.
        firefox_profile : FirefoxPreferences | FirefoxProfile | str, optional
            Profile applied through ``options.profile``.
        """
        super().__init__(
            service, options if options is not None else firefox_options, executable_path=executable_path
        )
        self.firefox_profile = firefox_profile

    def _build_options(self):
        options = _unwrap(self.options)
        if options is None:
            options = FirefoxOptionRaw()
        profile = _unwrap(self.firefox_profile)
        if profile is not None:
            options.profile = profile
        return options

    def _start(self, options, service):
        driver = super()._start(options, service)
        for extension in getattr(options, EXTENSIONS_ATTR, None) or []:
            driver.install_addon(extension, temporary=True)
        return driver


class Safari(_LocalDriver):

    _service_class = SafariServiceRaw
    _driver_class = webdriver.Safari

    def __init__(self, service: BrowserService = None, options: BrowserOptions = None) -> None:
        super().__init__(service, options)


class RemoteWebdriver(DriverInterface):

    def __init__(
        self,
        remote_url: str,
        options: BrowserOptions = None,
        keep_alive: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        remote_url : str
            Grid or remote driver URL; ``host:4444`` is accepted and normalised to ``http://host:4444``.
        options : BrowserOptions | selenium Options, optional
            Which browser to request; defaults to Chrome.
        keep_alive : bool, optional
            Reuse the HTTP connection to the grid.
        """
        self.remote_url = normalize_grid_url(remote_url)
        self.options = options
        self.keep_alive = keep_alive

    def factory(self) -> object:
        try:
            options = _unwrap(self.options)
            if options is None:
                options = ChromeOptionRaw()
            return webdriver.Remote(
                command_executor=self.remote_url,
                options=options,
                keep_alive=self.keep_alive,
            )
        except Exception:
            logger.exception("Failed to connect to remote WebDriver at %s", self.remote_url)
            raise


class Appium(DriverInterface):

    def __init__(
        self,
        remote_url: str,
        options: BrowserOptions = None,
        keep_alive: bool = False,
    ) -> None:
        self.remote_url = normalize_grid_url(remote_url)
        self.options = options
        self.keep_alive = keep_alive

    def factory(self) -> object:
        if appium_webdriver is None:
            raise ImportError("appium-python-client is required for Appium sessions")
        try:
            return appium_webdriver.Remote(
                command_executor=self.remote_url,
                options=_unwrap(self.options),
                keep_alive=self.keep_alive,
            )
        except Exception:
            logger.exception("Failed to connect to Appium at %s", self.remote_url)
            raise
