import base64
import contextlib
import functools
import logging
import random
import re
import shutil
import tempfile
import weakref
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    MoveTargetOutOfBoundsException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from ..dom import CachedElement, LocatedWebElement
from .driverinterface import Chrome, DriverInterface, Edge, Firefox, RemoteWebdriver
from .options import ChromeOptions, EdgeOptions, FirefoxOptions, SafariOptions
from .services import ChromeService, EdgeService, FirefoxService
from .types import DROPDOWNTYPE, MODIFERKEYS
from .wait import *
from .wait import _is_stale, _ready

try:
    import psutil
except ImportError:  # declared as a dependency, but tolerate a bare environment
    psutil = None

try:
    from appium.webdriver.common.appiumby import AppiumBy
except ImportError:  # appium-python-client is only needed for mobile sessions
    AppiumBy = None

_APPIUM_DEFAULT_BY = AppiumBy.IOS_PREDICATE if AppiumBy is not None else "-ios predicate string"

# Defined after ``from .wait import *`` on purpose: the star import also brings in wait.py's
# ``logger`` and this module must log under its own name.
logger = logging.getLogger(__name__)

# Click errors that a JavaScript click can work around (element off-screen, covered, or not
# considered interactable by the pointer-action implementation).
_CLICK_FALLBACK = (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    MoveTargetOutOfBoundsException,
)

_PAGE_HEIGHT_JS = "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
_PARTIAL_DOWNLOAD_SUFFIXES = (".crdownload", ".part", ".tmp", ".download")

# Injected on every new document when ``disable_bot_detection_flag`` is set: hides the
# ``navigator.webdriver`` flag, reports a plausible language list and device memory, and adds
# per-call noise to canvas fingerprints.
_STEALTH_SCRIPT = """
(function () {
    try { Object.defineProperty(navigator, 'webdriver', {get: function () { return false; }}); } catch (e) {}
    try { Object.defineProperty(navigator, 'languages', {get: function () { return ['en-US', 'en']; }}); } catch (e) {}
    try { Object.defineProperty(navigator, 'deviceMemory', {get: function () { return 8; }}); } catch (e) {}
    try { if (!window.chrome) { window.chrome = {runtime: {}}; } } catch (e) {}
    var overwrite = function (name) {
        var OLD = HTMLCanvasElement.prototype[name];
        if (!OLD) { return; }
        Object.defineProperty(HTMLCanvasElement.prototype, name, {
            value: function () {
                try {
                    var shift = {
                        r: Math.floor(Math.random() * 10) - 5,
                        g: Math.floor(Math.random() * 10) - 5,
                        b: Math.floor(Math.random() * 10) - 5,
                        a: Math.floor(Math.random() * 10) - 5
                    };
                    var width = this.width, height = this.height, context = this.getContext('2d');
                    if (context && width && height) {
                        var imageData = context.getImageData(0, 0, width, height);
                        for (var i = 0; i < height; i++) {
                            for (var j = 0; j < width; j++) {
                                var n = ((i * (width * 4)) + (j * 4));
                                imageData.data[n + 0] = imageData.data[n + 0] + shift.r;
                                imageData.data[n + 1] = imageData.data[n + 1] + shift.g;
                                imageData.data[n + 2] = imageData.data[n + 2] + shift.b;
                                imageData.data[n + 3] = imageData.data[n + 3] + shift.a;
                            }
                        }
                        context.putImageData(imageData, 0, 0);
                    }
                } catch (e) {}
                return OLD.apply(this, arguments);
            }
        });
    };
    overwrite('toBlob');
    overwrite('toDataURL');
})();
"""


class Error(Exception):
    def __init__(self, text):
        super().__init__(text)
        self.text = text


def _paced(method):
    """
    Sleep ``action_delay`` seconds before a mutating action.

    A depth counter makes nested paced calls (``find_and_click`` -> ``click_element``) sleep
    only once, and read-only methods are never decorated.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        self._pace()
        self._pace_depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._pace_depth -= 1

    return wrapper


class DriverClient(object):

    # Clients created in this process that have not been quit yet (see ``close_previous_sessions``).
    _live = weakref.WeakSet()

    _STATE_LOCATOR = {
        "present": EC.presence_of_element_located,
        "visible": EC.visibility_of_element_located,
        "clickable": EC.element_to_be_clickable,
    }
    _STATE_LOCATOR_ALL = {
        "present": EC.presence_of_all_elements_located,
        "visible": EC.visibility_of_all_elements_located,
        "enabled": AllElementsVisibleAndEnabled,
    }

    def __init__(self, driver: DriverInterface, poll_time: int = 10, poll_frequency: float = 0.5, scroll_pause_time: int = 5, debug_mode: bool = False, throw: bool = False,
                 delete_profile: bool = False, close_previous_sessions: bool = False, action_delay: float = 0, disable_bot_detection_flag: bool = False, default_by: By = By.XPATH,
                 keep_open: bool = False) -> None:
        """
        A client to interact with and manipulate web pages using Selenium.

        Parameters
        ----------
        driver : WebDriver
            A started Selenium WebDriver (the object returned by ``Chrome(...).factory()`` etc.).
        poll_time : int, optional
            Maximum time, in seconds, to wait for an element or condition, by default 10.
        poll_frequency : float, optional
            Sleep interval between condition checks, in seconds, by default 0.5.
        scroll_pause_time : int, optional
            Maximum time, in seconds, to wait for the page to grow after each scroll, by default 5.
        debug_mode : bool, optional
            If True, the driver is not quit when the client is deleted and tracebacks are logged, by default False.
        throw : bool, optional
            If True, failures raise ``Error``; otherwise they are logged and a falsy value is returned, by default False.
        delete_profile : bool, optional
            If True, the browser profile directory is removed after ``quit()``. Only a temporary
            profile (created by the driver) or the directory given to ``DriverClient.chrome(user_data_dir=...)``
            is ever removed, by default False.
        close_previous_sessions : bool, optional
            If True, other ``DriverClient`` instances created earlier in this process are quit first, by default False.
        action_delay : float, optional
            Seconds to sleep before every mutating action (click, type, navigate, scroll, switch), by default 0.
        disable_bot_detection_flag : bool, optional
            If True, hides the usual automation markers through CDP (Chromium browsers only), by default False.
        default_by : By, optional
            Locator strategy paired with bare locator strings, by default By.XPATH.
        keep_open : bool, optional
            If True, the browser is left open when the client is deleted or leaves a ``with`` block, by default False.

        Attributes
        ----------
        driver : WebDriver
            The underlying Selenium WebDriver.
        """
        self._pace_depth = 0
        self._closed = False
        self._profile_dir = None
        self._explicit_data_dir = None
        self.close_previous_sessions = close_previous_sessions
        self.debug_mode = debug_mode
        self.delete_profile = delete_profile
        self.driver = driver
        self.poll_frequency = poll_frequency
        self.poll_time = poll_time
        self.scroll_pause_time = scroll_pause_time
        self.throw = throw
        self.action_delay = action_delay
        self.disable_bot_detection_flag = disable_bot_detection_flag
        self.default_by = default_by
        self.keep_open = keep_open
        if driver is None:
            raise Error("DriverClient needs a started WebDriver; the driver factory returned None")
        if close_previous_sessions:
            self._close_previous_sessions()
        DriverClient._live.add(self)
        if delete_profile:
            self._profile_dir = self._profile_dir_from_capabilities()
        self.__setup()

    # ------------------------------------------------------------------ lifecycle

    def __del__(self) -> None:

        with contextlib.suppress(Exception):
            if not (self.debug_mode or self.keep_open):
                self.quit()
                self.driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if not (self.debug_mode or self.keep_open):
            with contextlib.suppress(Exception):
                self.quit()
        return False

    @classmethod
    def chrome(cls, arguments: list = None, preferences: dict = None, headless: bool = False, user_agent: str = None,
               proxy: str = None, download_dir: str = None, user_data_dir: str = None, profile_directory: str = None,
               executable_path: str = None, binary_path: str = None, extension_paths: list = None,
               performance_logging: bool = False, window_size: tuple = None, page_load_strategy: str = None,
               **client_kwargs) -> "DriverClient":
        """
        Start a local Chrome and wrap it in a client in one call.

        The option arguments map onto ``ChromeOptions``; everything in ``client_kwargs`` goes to the
        ``DriverClient`` constructor (``poll_time``, ``throw``, ``delete_profile``, ...). Without
        ``executable_path`` Selenium Manager downloads a chromedriver that matches the installed browser.
        """
        options = ChromeOptions(
            arguments, preferences, extension_paths, binary_path,
            client_kwargs.get("disable_bot_detection_flag", False), client_kwargs.get("debug_mode", False),
            headless=headless, user_agent=user_agent, proxy=proxy, window_size=window_size, download_dir=download_dir,
            page_load_strategy=page_load_strategy, performance_logging=performance_logging,
            user_data_dir=user_data_dir, profile_directory=profile_directory,
        )
        service = ChromeService(executable_path) if executable_path else None
        client = cls(Chrome(service=service, options=options).factory(), **client_kwargs)
        client._explicit_data_dir = str(user_data_dir) if user_data_dir else None
        return client

    @classmethod
    def edge(cls, arguments: list = None, preferences: dict = None, headless: bool = False, user_agent: str = None,
             proxy: str = None, download_dir: str = None, user_data_dir: str = None, profile_directory: str = None,
             executable_path: str = None, binary_path: str = None, extension_paths: list = None,
             performance_logging: bool = False, window_size: tuple = None, page_load_strategy: str = None,
             **client_kwargs) -> "DriverClient":
        """Start a local Microsoft Edge and wrap it in a client; see ``chrome`` for the arguments."""
        options = EdgeOptions(
            arguments, preferences, extension_paths, binary_path,
            client_kwargs.get("disable_bot_detection_flag", False), client_kwargs.get("debug_mode", False),
            headless=headless, user_agent=user_agent, proxy=proxy, window_size=window_size, download_dir=download_dir,
            page_load_strategy=page_load_strategy, performance_logging=performance_logging,
            user_data_dir=user_data_dir, profile_directory=profile_directory,
        )
        service = EdgeService(executable_path) if executable_path else None
        client = cls(Edge(service=service, options=options).factory(), **client_kwargs)
        client._explicit_data_dir = str(user_data_dir) if user_data_dir else None
        return client

    @classmethod
    def firefox(cls, arguments: list = None, headless: bool = False, user_agent: str = None, proxy: str = None,
                download_dir: str = None, preferences: dict = None, profile_directory: str = None,
                executable_path: str = None, binary_path: str = None, extension_paths: list = None,
                **client_kwargs) -> "DriverClient":
        """Start a local Firefox and wrap it in a client; see ``chrome`` for the arguments."""
        options = FirefoxOptions(
            arguments, extension_paths, headless=headless, user_agent=user_agent, proxy=proxy,
            download_dir=download_dir, preferences=preferences, profile_directory=profile_directory,
            binary_path=binary_path,
        )
        service = FirefoxService(executable_path) if executable_path else None
        return cls(Firefox(service=service, options=options).factory(), **client_kwargs)

    @classmethod
    def remote(cls, grid_url: str, browser: str = "chrome", arguments: list = None, headless: bool = False,
               user_agent: str = None, proxy: str = None, keep_alive: bool = False, options=None,
               **client_kwargs) -> "DriverClient":
        """
        Connect to a Selenium Grid / remote WebDriver and wrap the session in a client.

        ``browser`` is ``"chrome"``, ``"edge"``, ``"firefox"`` or ``"safari"``; pass ``options``
        (a wrapper or raw Selenium options) to control the session in full.
        """
        if options is None:
            name = (browser or "chrome").lower()
            if name == "chrome":
                options = ChromeOptions(arguments, headless=headless, user_agent=user_agent, proxy=proxy)
            elif name in ("edge", "msedge", "microsoftedge"):
                options = EdgeOptions(arguments, headless=headless, user_agent=user_agent, proxy=proxy)
            elif name == "firefox":
                options = FirefoxOptions(arguments, headless=headless, user_agent=user_agent, proxy=proxy)
            elif name == "safari":
                options = SafariOptions(arguments)
            else:
                raise Error(f"Unknown browser for a remote session: {browser}")
        driver = RemoteWebdriver(grid_url, options=options, keep_alive=keep_alive).factory()
        return cls(driver, **client_kwargs)

    def _close_previous_sessions(self) -> None:
        for other in list(DriverClient._live):
            if other is self or other._closed or other.debug_mode or other.keep_open:
                continue
            with contextlib.suppress(Exception):
                other.quit()

    def _profile_dir_from_capabilities(self):
        """The profile directory the driver reports for this session, or None."""
        caps = getattr(self.driver, "capabilities", None) or {}
        name = str(caps.get("browserName", "")).lower()
        path = None
        if name == "chrome":
            path = (caps.get("chrome") or {}).get("userDataDir")
        elif name in ("msedge", "microsoftedge"):
            path = (caps.get("msedge") or {}).get("userDataDir")
        elif name == "firefox":
            path = caps.get("moz:profile")
        return Path(path) if path else None

    def _kill_processes(self):
        """
        Kill the driver service process and its children.

        Belt and braces after ``quit()``; a no-op for remote sessions or when psutil is missing.
        Never raises.
        """
        if psutil is None:
            return
        with contextlib.suppress(Exception):
            service = getattr(self.driver, "service", None)
            process = getattr(service, "process", None)
            pid = getattr(process, "pid", None)
            if pid:
                p = psutil.Process(pid)
                children = p.children(recursive=True)
                children.append(p)
                for process in children:
                    with contextlib.suppress(Exception):
                        process.kill()

    def _delete_profile(self):
        """
        Remove the session's profile directory. Idempotent and never raises.

        Only a directory under the system temp directory (the ones the drivers create) or the
        directory given to ``DriverClient.chrome(user_data_dir=...)`` is removed; anything else is
        left alone with a warning so a real browser profile can never be deleted by accident.
        """
        with contextlib.suppress(Exception):
            path = self._profile_dir or self._profile_dir_from_capabilities()
            self._profile_dir = None
            if not path or not path.exists():
                return
            if not hasattr(self.driver, "service"):
                logger.debug("delete_profile: remote session, no local profile to remove")
                return
            resolved = path.resolve()
            temp_root = Path(tempfile.gettempdir()).resolve()
            explicit = Path(self._explicit_data_dir).resolve() if self._explicit_data_dir else None
            if not (resolved.is_relative_to(temp_root) or (explicit is not None and resolved == explicit)):
                logger.warning("delete_profile: refusing to remove non-temporary profile %s", path)
                return
            shutil.rmtree(resolved, ignore_errors=True)

    def __setup(self):
        if not self.disable_bot_detection_flag:
            return
        try:
            if not hasattr(self.driver, "execute_cdp_cmd"):
                logger.debug("disable_bot_detection_flag: this driver has no CDP support, skipping")
                return
            user_agent = self.driver.execute_script("return navigator.userAgent;") or ""
            if "HeadlessChrome" in user_agent:
                user_agent = user_agent.replace("HeadlessChrome", "Chrome")
            if user_agent:
                self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent})
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _STEALTH_SCRIPT})
            # Patch the document that is already open as well.
            self.driver.execute_script(_STEALTH_SCRIPT)
        except Exception as err:
            logger.warning("Failed to apply the bot-detection countermeasures: %s", err)

    # ------------------------------------------------------------------ shared helpers

    def check_throw(self, error: Error) -> None:
        """Log ``error`` and raise it when the client was built with ``throw=True``."""
        self._fail(error.text, error=error)

    def _fail(self, message: str, err: Exception | None = None, *, error: Error | None = None):
        """
        Record a failure: one log line, a traceback only in ``debug_mode``, raise when ``throw``.

        Returns None so callers can ``return self._fail(...)`` and keep the falsy contract.
        """
        if error is None:
            error = Error(message if err is None else f"{message} Error: {err}")
        logger.error(error.text)
        if self.debug_mode:
            logger.debug("Traceback for: %s", error.text, exc_info=err if err is not None else True)
        if self.throw:
            raise error from err
        return None

    def _pace(self) -> None:
        if self.action_delay and self.action_delay > 0 and self._pace_depth == 0:
            sleep(self.action_delay)

    def _timeout(self, timeout: float | None = None) -> float:
        """Resolve an optional per-call timeout to the client's default poll_time."""
        return self.poll_time if timeout is None else timeout

    def _wait(self, timeout: float | None = None) -> WebDriverWait:
        """A WebDriverWait using the client's poll_frequency and the given (or default) timeout."""
        return WebDriverWait(self.driver, self._timeout(timeout), poll_frequency=self.poll_frequency)

    def _locator(self, target: Any) -> tuple:
        """
        Normalize a locator argument to a (By, value) tuple.

        Accepts a bare locator string (paired with default_by) or an explicit (By, value) tuple/list,
        such as the one returned by LocatedWebElement.get_locator().
        """
        if isinstance(target, (tuple, list)) and len(target) == 2:
            return tuple(target)
        if isinstance(target, str):
            return (self.default_by, target)
        raise TypeError(f"Expected a locator string or a (By, value) tuple, got {type(target).__name__}")

    def _find(self, target: Any, timeout: float | None = None, state: str = "clickable") -> WebElement:
        """
        One WebDriverWait for an element in the given ``state`` (``present``, ``visible`` or ``clickable``).

        ``target`` is a locator string, a (By, value) tuple or an already located WebElement.
        Raises (usually ``TimeoutException``); callers decide whether to swallow.
        """
        if isinstance(target, WebElement):
            if state == "clickable":
                condition = EC.element_to_be_clickable(target)
            elif state == "visible":
                condition = EC.visibility_of(target)
            else:
                condition = lambda driver: False if _is_stale(target) else target
        else:
            condition = self._STATE_LOCATOR[state](self._locator(target))
        return self._wait(timeout).until(condition)

    def _find_all(self, target: Any, timeout: float | None = None, state: str = "present") -> list:
        """One WebDriverWait for a non-empty list of elements (``present``, ``visible`` or ``enabled``)."""
        return self._wait(timeout).until(self._STATE_LOCATOR_ALL[state](self._locator(target)))

    def _do_with_element(self, target: Any, action: Callable, timeout: float | None = None, state: str = "clickable"):
        """Find ``target`` and apply ``action`` to it, re-finding once if the element went stale in between."""
        element = self._find(target, timeout, state)
        try:
            return action(element)
        except StaleElementReferenceException:
            if isinstance(target, WebElement):
                raise
            return action(self._find(target, timeout, state))

    def _scroll_into_view(self, element: WebElement) -> None:
        """Scroll ``element`` to the middle of the viewport with JavaScript (works for off-screen targets in every browser)."""
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element)

    def _pointer(self, element: WebElement, compose: Callable, js_fallback: str | None = None) -> None:
        """
        Run a pointer action on ``element``: scroll to it, move the mouse over it, then whatever
        ``compose(action_chain, element)`` adds (click, double click, ...), all in one WebDriver command.

        geckodriver rejects a wheel scroll or pointer move whose target is outside the viewport
        (``MoveTargetOutOfBoundsException``); the element is then scrolled into view with
        JavaScript and the pointer action is retried, so the page still receives real pointer
        events. If it still fails and ``js_fallback`` is given, that script runs with the element
        as ``arguments[0]``.
        """
        try:
            try:
                chain = ActionChains(self.driver).scroll_to_element(element).move_to_element(element)
                compose(chain, element).perform()
            except MoveTargetOutOfBoundsException:
                self._scroll_into_view(element)
                compose(ActionChains(self.driver).move_to_element(element), element).perform()
        except _CLICK_FALLBACK as err:
            if js_fallback is None:
                raise
            logger.debug("Pointer action failed (%s); falling back to JavaScript", type(err).__name__)
            self.driver.execute_script(js_fallback, element)

    def _perform_click(self, element: WebElement, js_fallback: bool = True) -> None:
        """
        Scroll to, hover over and click an element with ActionChains. Raises on failure.

        When the pointer action fails because the element is off-screen or not interactable
        (``MoveTargetOutOfBounds``, ``ElementNotInteractable``, ``ElementClickIntercepted``) and
        ``js_fallback`` is set, the click is retried through JavaScript. Pointer actions cannot
        detect an overlay covering the target; use ``js_click`` when that is the problem.
        """
        self._pointer(element, lambda chain, target: chain.click(target),
                      "arguments[0].click();" if js_fallback else None)

    def _script(self, script: str, *args) -> Any:
        """Run JavaScript with positional arguments exposed as ``arguments[n]``."""
        return self.driver.execute_script(script, *args)

    def _wait_for_growth(self, measure: Callable[[], Any], baseline: Any, settle_polls: int = 1) -> Any:
        """
        Poll ``measure()`` every poll_frequency for up to scroll_pause_time seconds.

        Returns the first reading that differs from ``baseline`` once it has stayed the same for
        ``settle_polls`` further polls, or the last reading when the time is up.
        """
        deadline = monotonic() + max(self.scroll_pause_time or 0, 0)
        current = baseline
        stable = 0
        reading = baseline
        while True:
            sleep(self.poll_frequency)
            reading = measure()
            if reading != baseline:
                if reading == current:
                    stable += 1
                    if stable >= settle_polls:
                        return reading
                else:
                    current = reading
                    stable = 0
            if monotonic() >= deadline:
                return reading

    # ------------------------------------------------------------------ window and navigation

    def maximize_window(self):
        """Maximize the current browser window."""
        try:
            self.driver.maximize_window()
        except Exception as err:
            self._fail("Failed to maximize the window.", err)

    def close(self) -> None:
        """Close the current browser window (the session stays alive)."""
        try:
            self.driver.close()
        except Exception as err:
            self._fail("Failed to close the window.", err)

    def quit(self) -> None:
        """
        Quit the driver session, then remove the profile (when ``delete_profile``) and stop any
        leftover driver processes. Safe to call more than once.
        """
        if self._closed:
            return
        try:
            self.driver.quit()
        except Exception as err:
            self._fail("Failed to quit the driver.", err)
        finally:
            self._closed = True
            if self.delete_profile:
                self._delete_profile()
            self._kill_processes()
            with contextlib.suppress(Exception):
                DriverClient._live.discard(self)

    @_paced
    def go(self, url: str) -> None:
        """Navigate to ``url``."""
        try:
            self.driver.get(url)
        except Exception as err:
            self._fail(f"Failed to open {url}.", err)

    @_paced
    def go_and_wait_for_load(self, url: str, timeout: float | None = None) -> None:
        """Navigate to ``url`` and wait until ``document.readyState`` is ``complete``."""
        try:
            self.driver.get(url)
            self._wait(timeout).until(WaitForPageLoad())
        except Exception as err:
            self._fail(f"Failed to open {url} and wait for it to load.", err)

    @_paced
    def reload(self) -> None:
        """Reload the current page."""
        try:
            self.driver.refresh()
        except Exception as err:
            self._fail("Failed to reload the page.", err)

    def refresh(self) -> None:
        """Alias of ``reload``."""
        return self.reload()

    @_paced
    def back(self) -> None:
        """Go back one entry in the browser history."""
        try:
            self.driver.back()
        except Exception as err:
            self._fail("Failed to go back.", err)

    @_paced
    def forward(self) -> None:
        """Go forward one entry in the browser history."""
        try:
            self.driver.forward()
        except Exception as err:
            self._fail("Failed to go forward.", err)

    def get_title(self) -> str | None:
        """The current page title, or None if it cannot be read."""
        try:
            return self.driver.title
        except Exception as err:
            return self._fail("Failed to read the page title.", err)

    def get_page_source(self) -> str | None:
        """The current page's HTML source, or None if it cannot be read."""
        try:
            return self.driver.page_source
        except Exception as err:
            return self._fail("Failed to read the page source.", err)

    def set_timeouts(self, page_load: float | None = None, script: float | None = None, implicit: float | None = None) -> None:
        """
        Set the driver's own timeouts (seconds). Leave ``implicit`` at 0 unless you know you
        need it: an implicit wait adds to every explicit wait this client performs.
        """
        try:
            if page_load is not None:
                self.driver.set_page_load_timeout(page_load)
            if script is not None:
                self.driver.set_script_timeout(script)
            if implicit is not None:
                self.driver.implicitly_wait(implicit)
        except Exception as err:
            self._fail("Failed to set the driver timeouts.", err)

    def pause(self, seconds: float | tuple) -> None:
        """Sleep ``seconds``, or a random duration from a ``(low, high)`` pair (human-like pacing)."""
        if isinstance(seconds, (tuple, list)):
            low, high = seconds
            seconds = random.uniform(float(low), float(high))
        if seconds and seconds > 0:
            sleep(seconds)

    # ------------------------------------------------------------------ scrolling

    @_paced
    def scroll_to_top(self) -> None:
        """Scroll the window to the top of the page."""
        try:
            self._script("window.scrollTo(0, 0);")
        except Exception as err:
            self._fail("Failed to scroll to the top.", err)

    @_paced
    def scroll_to_bottom(self, times: int, settle_polls: int = 1) -> None:
        """
        Scroll to the bottom of the page up to ``times`` times, giving lazy-loaded content a chance
        to appear after each scroll.

        After every scroll the page height is polled every ``poll_frequency`` for at most
        ``scroll_pause_time`` seconds; the loop stops early as soon as the height no longer grows.

        Args:
            times (int): Maximum number of scrolls.
            settle_polls (int): Extra polls the new height must hold before it counts as loaded.
        """
        try:
            browser_height = self._script(_PAGE_HEIGHT_JS)
            for _ in range(times):
                self._script("window.scrollTo(0, arguments[0]);", browser_height)
                new_browser_height = self._wait_for_growth(lambda: self._script(_PAGE_HEIGHT_JS), browser_height, settle_polls)
                if new_browser_height == browser_height:
                    break
                browser_height = new_browser_height
        except Exception as err:
            self._fail("Failed to scroll to the bottom.", err)

    @_paced
    def scroll_to_bottom_watch_element_height(self, times: int, locator: str, settle_polls: int = 1, timeout: float | None = None) -> None:
        """
        Scroll to the bottom of the page up to ``times`` times while watching the height of the
        element matching ``locator`` (a container that grows as items load).

        Args:
            times (int): Maximum number of scrolls.
            locator (str): Locator of the element to watch (``default_by`` or a (By, value) tuple).
            settle_polls (int): Extra polls the new height must hold before it counts as loaded.
            timeout (float, optional): Seconds to wait for the element, by default poll_time.
        """
        try:
            state = {"element": self._find(locator, timeout, "present")}

            def measure():
                try:
                    return self._script("return arguments[0].scrollHeight;", state["element"])
                except StaleElementReferenceException:
                    state["element"] = self._find(locator, timeout, "present")
                    return self._script("return arguments[0].scrollHeight;", state["element"])

            element_height = measure()
            for _ in range(times):
                self._script("window.scrollTo(0, arguments[0]);", self._script(_PAGE_HEIGHT_JS))
                new_element_height = self._wait_for_growth(measure, element_height, settle_polls)
                if new_element_height == element_height:
                    break
                element_height = new_element_height
        except Exception as err:
            self._fail(f"Failed to scroll while watching {locator}.", err)

    @_paced
    def scroll_to_element(self, target: Any, timeout: float | None = None) -> None:
        """
        Scroll the element into view.

        Args:
            target (str | tuple | WebElement): Locator or element to scroll to.
            timeout (float, optional): Seconds to wait for the element, by default poll_time.
        """
        try:
            element = target if isinstance(target, WebElement) else self._find(target, timeout, "present")
            try:
                ActionChains(self.driver).scroll_to_element(element).perform()
            except MoveTargetOutOfBoundsException:
                # geckodriver refuses a wheel scroll whose origin element is off-screen
                self._scroll_into_view(element)
        except Exception as err:
            self._fail(f"Failed to scroll to {target}.", err)

    # ------------------------------------------------------------------ tabs, windows and frames

    @_paced
    def open_new_tab(self) -> None:
        """Open a new blank tab with ``window.open()``; focus stays on the current tab."""
        try:
            self._script("window.open();")
        except Exception as err:
            self._fail("Failed to open a new tab.", err)

    @_paced
    def open_new_tab_go(self, url: str) -> None:
        """Open a new tab at ``url`` with ``window.open()``; focus stays on the current tab."""
        try:
            self._script("var newWindow = window.open(); newWindow.location.href = arguments[0];", url)
        except Exception as err:
            self._fail(f"Unable to open new tab to {url}.", err)

    @contextlib.contextmanager
    def new_tab(self, url: str | None = None, close: bool = True):
        """
        Open a new tab, switch to it for the duration of the ``with`` block, then (by default)
        close it and switch back to the tab that was active before.

        Yields the new tab's window handle. Opening the tab raises regardless of ``throw``.
        """
        origin = self.driver.current_window_handle
        self.driver.switch_to.new_window("tab")
        handle = self.driver.current_window_handle
        if url:
            self.driver.get(url)
        try:
            yield handle
        finally:
            with contextlib.suppress(WebDriverException):
                if close and handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
                handles = self.driver.window_handles
                self.driver.switch_to.window(origin if origin in handles else handles[0])

    def get_current_iframe(self) -> str | None:
        """The ``window.name`` of the current browsing context ("" for the top document)."""
        try:
            return self._script("return window.name;")
        except Exception as err:
            return self._fail("Failed to read the current frame name.", err)

    @_paced
    def switch_to_iframe(self, iframe: Any, timeout: float | None = None) -> None:
        """
        Switch the driver's focus to an iframe.

        Args:
            iframe (WebElement | str | tuple): The iframe element, or a locator for it.
            timeout (float, optional): Seconds to wait for the frame element, by default poll_time.
        """
        try:
            element = iframe if isinstance(iframe, WebElement) else self._find(iframe, timeout, "present")
            self.driver.switch_to.frame(element)
        except Exception as err:
            self._fail("Failed to switch to the iframe.", err)

    @_paced
    def switch_to_default_iframe(self) -> None:
        """Switch the driver's focus back to the top document."""
        try:
            self.driver.switch_to.default_content()
        except Exception as err:
            self._fail("Failed to switch to the default content.", err)

    @_paced
    def switch_to_parent_frame(self) -> None:
        """Switch the driver's focus to the parent of the current frame."""
        try:
            self.driver.switch_to.parent_frame()
        except Exception as err:
            self._fail("Failed to switch to the parent frame.", err)

    @contextlib.contextmanager
    def frame(self, target: Any, timeout: float | None = None):
        """
        Switch into a frame for the duration of the ``with`` block and switch back to its parent afterwards.

        Args:
            target (str | tuple | WebElement | int): Locator, element or index of the frame.
            timeout (float, optional): Seconds to wait for the frame, by default poll_time.

        Entering raises regardless of ``throw`` (the block cannot run without the frame);
        leaving never raises. Nest ``with client.frame(...)`` blocks to descend several levels.
        """
        locator = self._locator(target) if isinstance(target, (str, tuple, list)) else target
        self._wait(timeout).until(EC.frame_to_be_available_and_switch_to_it(locator))
        try:
            yield self
        finally:
            with contextlib.suppress(WebDriverException):
                self.driver.switch_to.parent_frame()

    @_paced
    def find_frame_switch(self, locator: str, timeout: float | None = None) -> None:
        """Wait for the frame matching ``locator`` to be available and switch into it."""
        try:
            self._wait(timeout).until(
                EC.frame_to_be_available_and_switch_to_it(self._locator(locator)))
        except Exception as err:
            self._fail(f"Failed to find frame: {locator} and switch.", err)

    def get_window_handles(self):
        """All window handles of the session."""
        try:
            return self.driver.window_handles
        except Exception as err:
            return self._fail("Failed to get current window handles.", err)

    def get_current_window_handle(self):
        """The handle of the focused window."""
        try:
            return self.driver.current_window_handle
        except Exception as err:
            return self._fail("Failed to save current window handle.", err)

    def get_window_handle_id(self, index: int) -> str | None:
        """The window handle at ``index``."""
        try:
            return self.driver.window_handles[index]
        except Exception as err:
            return self._fail(f"No window at index {index}.", err)

    @_paced
    def find_window_handle_switch_to_it_close_previous(self, index: int, timeout: float | None = None) -> None:
        """Switch to the window at ``index`` and close the window that was focused before."""
        try:
            self._wait(timeout).until(
                WindowHandleToBeAvailableSwitchClosePrevious(index))
        except Exception as err:
            self._fail(f"Failed to find window index: {index} and switch.", err)

    @_paced
    def find_window_handle_switch_to_it(self, index: int, timeout: float | None = None) -> None:
        """Wait for a window to exist at ``index`` and switch to it."""
        try:
            window = self._wait(timeout).until(WindowHandleToBeAvailable(index))
            self.driver.switch_to.window(window)
        except Exception as err:
            self._fail(f"Failed to find window index: {index} and switch.", err)

    @_paced
    def switch_to_latest_window(self, previous_handles=None, timeout: float | None = None) -> None:
        """
        Switch to the newest window.

        Args:
            previous_handles (iterable, optional): Handles captured before the action that opened
                the window (``get_window_handles()``); when given, waits for a handle that is not in it.
                Without it the last handle is used immediately.
            timeout (float, optional): Seconds to wait, by default poll_time.
        """
        try:
            if previous_handles is not None:
                window = self._wait(timeout).until(NewWindowOpened(previous_handles))
            else:
                window = self._wait(timeout).until(
                    WindowHandleToBeAvailable(len(self.driver.window_handles) - 1))
            self.driver.switch_to.window(window)
        except Exception as err:
            self._fail("Failed to switch to the latest window.", err)

    @_paced
    def switch_to_first_window(self) -> None:
        """Switch to the first window of the session."""
        try:
            first_window_index = self.driver.window_handles[0]
            self.driver.switch_to.window(first_window_index)
        except Exception as err:
            self._fail("Failed to switch to the first window.", err)

    def close_current_window(self) -> None:
        """Close the focused window (the session stays alive)."""
        try:
            self.driver.close()
        except Exception as err:
            self._fail("Failed to close the current window.", err)

    def wait_for_new_window(self, previous_handles, timeout: float | None = None) -> str | None:
        """
        Wait for a window handle that is not in ``previous_handles`` and return it (without switching).

        Returns:
            str | None: The new handle, or None on timeout when throw is False.
        """
        try:
            return self._wait(timeout).until(NewWindowOpened(previous_handles))
        except Exception as err:
            return self._fail(f"No new window appeared within {self._timeout(timeout)}s.", err)

    def _switch_to_window_matching(self, predicate: Callable, timeout: float | None) -> str:
        origin = self.driver.current_window_handle

        def condition(driver):
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                if predicate(driver):
                    return handle
            if origin in driver.window_handles:
                driver.switch_to.window(origin)
            return False

        return self._wait(timeout).until(condition)

    @_paced
    def switch_to_window_by_title(self, text: str, timeout: float | None = None) -> bool:
        """Switch to the first window whose title contains ``text``."""
        try:
            self._switch_to_window_matching(lambda driver: text in (driver.title or ""), timeout)
            return True
        except Exception as err:
            self._fail(f"No window with a title containing {text!r} within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def switch_to_window_by_url(self, text: str, timeout: float | None = None) -> bool:
        """Switch to the first window whose URL contains ``text``."""
        try:
            self._switch_to_window_matching(lambda driver: text in (driver.current_url or ""), timeout)
            return True
        except Exception as err:
            self._fail(f"No window with a URL containing {text!r} within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def close_other_windows(self) -> None:
        """Close every window except the focused one."""
        try:
            current = self.driver.current_window_handle
            for handle in self.driver.window_handles:
                if handle != current:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
            self.driver.switch_to.window(current)
        except Exception as err:
            self._fail("Failed to close the other windows.", err)

    @contextlib.contextmanager
    def window(self, handle: Any, timeout: float | None = None):
        """
        Switch to a window (handle or index) for the duration of the ``with`` block and switch back afterwards.

        Entering raises regardless of ``throw``; leaving never raises. If the original window was
        closed inside the block, focus moves to the first remaining window.
        """
        origin = self.driver.current_window_handle
        if isinstance(handle, int):
            handle = self._wait(timeout).until(WindowHandleToBeAvailable(handle))
        else:
            self._wait(timeout).until(lambda driver: handle in driver.window_handles)
        self.driver.switch_to.window(handle)
        try:
            yield handle
        finally:
            with contextlib.suppress(WebDriverException):
                handles = self.driver.window_handles
                self.driver.switch_to.window(origin if origin in handles else handles[0])

    ## ELEMENT FUNCTIONS ##

    @_paced
    def press_modifer_key_send_keys(
            self, modifer_key: MODIFERKEYS, keys: Any = "") -> None:
        """Hold ``modifer_key`` while sending ``keys``, then release it."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key).send_keys(keys).key_up(modifer_key)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to press {modifer_key!r} and send keys {keys!r}.", err)

    @_paced
    def press_modifer_key(self, modifer_key: MODIFERKEYS) -> None:
        """Press and release ``modifer_key``."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key).key_up(modifer_key)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to press {modifer_key!r}.", err)

    @_paced
    def press_modifer_key_send_keys_on_element(
            self, element: WebElement, modifer_key: MODIFERKEYS, keys: Any = "") -> None:
        """Hold ``modifer_key`` while sending ``keys`` to ``element``, then release it."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key, element).send_keys(
                keys, element).key_up(modifer_key, element)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to press {modifer_key!r} and send keys {keys!r} on the element.", err)

    @_paced
    def press_modifer_key_on_element(
            self, element: WebElement, modifer_key: MODIFERKEYS) -> None:
        """Press and release ``modifer_key`` on ``element``."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key, element).key_up(modifer_key, element)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to press {modifer_key!r} on the element.", err)

    def get_elements(self, locator: str, timeout: float | None = None) -> list[LocatedWebElement] | None:
        """
        Wait until every element matching ``locator`` is visible and enabled and return them.

        One wait polls all of them together (``AllElementsVisibleAndEnabled``) instead of a
        separate clickable wait per element.

        Args:
            locator (str): The locator of the elements.
            timeout (float, optional): Seconds to wait, by default poll_time.

        Returns:
            list[LocatedWebElement] | None: The elements (each remembers its locator), or None on failure when throw is False.
        """
        try:
            locator_tuple = self._locator(locator)
            elements = self._find_all(locator_tuple, timeout, "enabled")
            return [
                LocatedWebElement(self.driver, element.id, locator_tuple) for element in elements
            ]
        except Exception as err:
            return self._fail(f"Failed to find elements: {locator}.", err)

    def get_elements_until_none(self, locator: str, timeout: float | None = None) -> list | bool:
        """
        Wait until at least one element matches ``locator`` and return the matches.

        Returns:
            list[WebElement] | bool: The elements, or False when none appeared (throw is False).
        """
        try:
            elements = self._wait(timeout).until(
                PresenceOfAllElementsLocatedIfNotEmpty(self._locator(locator)))
            return elements if isinstance(elements, list) else False
        except Exception as err:
            self._fail(f"Failed to find elements: {locator}.", err)
            return False

    def get_element_relative(
            self, parent_element: WebElement, locator: str) -> WebElement | None:
        """Find a child of ``parent_element`` (no waiting); None if absent."""
        try:
            return parent_element.find_element(*self._locator(locator))
        except Exception as err:
            return self._fail(f"Failed to find relative element: {locator}.", err)

    def get_element(self, locator: str, timeout: float | None = None) -> WebElement | None:
        """
        Wait until the element matching ``locator`` is clickable and return it.

        Returns:
            WebElement | None: The element, or None on timeout when throw is False.
        """
        try:
            return self._find(locator, timeout, "clickable")
        except Exception as err:
            return self._fail(f"Failed to find element: {locator}.", err)

    def try_to_get_element(self, locator: str, timeout: float | None = None) -> WebElement | bool:
        """Like ``get_element`` but never raises or logs; returns False when not found."""
        try:
            return self._find(locator, timeout, "clickable")
        except Exception:
            return False

    def get_element_by_tag_name(self, tag: str, timeout: float | None = None) -> WebElement | None:
        """The first element with the given tag name, or None."""
        try:
            return self._find((By.TAG_NAME, tag), timeout, "present")
        except Exception as err:
            return self._fail(f"Failed to find element by tag: {tag}.", err)

    def get_child_element(self, element: WebElement, locator: str, timeout: float | None = None) -> WebElement | None:
        """Find a child of ``element`` matching ``locator`` and wait for it to be clickable."""
        try:
            c_element = element.find_element(*self._locator(locator))
            return self._wait(timeout).until(EC.element_to_be_clickable(c_element))
        except Exception as err:
            return self._fail(f"Failed to find element: {locator}.", err)

    @_paced
    def find_and_send_modifer_key(self, locator: str, key: Any, timeout: float | None = None) -> None:
        """Find the element matching ``locator`` (clickable) and send ``key`` to it."""
        try:
            self._do_with_element(locator, lambda element: element.send_keys(key), timeout)
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and send keys: {key!r}.", err)

    @_paced
    def send_modifer_key_to_element(
            self, element: WebElement, modifier_key: Any, timeout: float | None = None) -> None:
        """Wait for ``element`` to be clickable and send ``modifier_key`` to it."""
        try:
            self._find(element, timeout, "clickable").send_keys(modifier_key)
        except Exception as err:
            self._fail(f"Failed to send keys {modifier_key!r} to the element.", err)

    @_paced
    def send_modifer_key(self, modifier_key) -> None:
        """Press and release ``modifier_key`` (same as ``press_modifer_key``)."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifier_key).key_up(modifier_key)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to send key {modifier_key!r}.", err)

    @_paced
    def send_modifer_key_to_window(self, window, modifier_key) -> None:
        """Press and release ``modifier_key`` on the given element."""
        try:
            action = ActionChains(self.driver)
            action.key_down(modifier_key, window).key_up(modifier_key, window)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to send key {modifier_key!r} to the element.", err)

    @_paced
    def find_and_click_send_modifer_key(
            self, locator: str, modifer_key: Any, keys: Any, timeout: float | None = None) -> None:
        """Click the element matching ``locator`` then hold ``modifer_key`` while sending ``keys``."""
        try:
            self._do_with_element(locator, self._perform_click, timeout)
            action = ActionChains(self.driver)
            action.key_down(modifer_key).send_keys(keys).key_up(modifer_key)
            action.perform()
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and send keys: {keys!r}.", err)

    @_paced
    def find_and_send_keys(self, locator: str, keys: Any, timeout: float | None = None) -> None:
        """
        Find the element matching ``locator``, type ``keys`` into it and verify the value.

        Args:
            locator (str): The locator of the element.
            keys (Any): The keys to send.
            timeout (float, optional): Seconds to wait, by default poll_time.
        """
        try:
            locator_tuple = self._locator(locator)
            element = self._find(locator_tuple, timeout, "clickable")
            self._wait(timeout).until(WaitForKeysVerification(locator_tuple, keys, element=element))
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and send keys: {keys!r}.", err)

    @_paced
    def find_and_send_keys_with_delay(
            self, locator: str, keys: Any, delay: float = 0.1, timeout: float | None = None) -> None:
        """
        Like ``find_and_send_keys`` but presses the keys one at a time with a random pause of up
        to ``delay`` seconds between them.
        """
        try:
            locator_tuple = self._locator(locator)
            element = self._find(locator_tuple, timeout, "clickable")
            self._wait(timeout).until(
                WaitForKeysVerificationWithDelay(locator_tuple, keys, delay, element=element))
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and send keys: {keys!r}.", err)

    @_paced
    def find_click_and_send_keys(self, locator: str, keys: str, timeout: float | None = None) -> None:
        """Find the element matching ``locator``, click it, type ``keys`` and verify the value."""
        try:
            locator_tuple = self._locator(locator)
            element = self._find(locator_tuple, timeout, "clickable")
            self._perform_click(element)
            self._wait(timeout).until(
                WaitForKeysVerification(locator_tuple, keys, click=False, element=element))
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and send keys: {keys!r}.", err)

    @_paced
    def find_and_click(self, locator: str, timeout: float | None = None) -> None:
        """Wait for the element matching ``locator`` to be clickable and click it."""
        try:
            self._do_with_element(locator, self._perform_click, timeout)
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and click.", err)

    @_paced
    def find_and_click_and_wait_for_element(
            self, locator: str, element_locator: str, timeout: float | None = None) -> None:
        """Click the element matching ``locator`` then wait for ``element_locator`` to be present."""
        try:
            self._do_with_element(locator, self._perform_click, timeout)
            self._wait(timeout).until(
                EC.presence_of_element_located(self._locator(element_locator)))
        except Exception as err:
            self._fail(f"Failed to click {locator} and find {element_locator}.", err)

    @_paced
    def find_click_and_send_keys_and_go(
            self, locator: str, keys: str, url: str, timeout: float | None = None) -> None:
        """
        Find an element, click it, send keys to it (verified), then navigate to a URL.

        Args:
            locator (str): The locator of the element to click and type into.
            keys (str): The keys to send to the element.
            url (str): The URL to navigate to afterwards.
            timeout (float, optional): Seconds to wait, by default poll_time.
        """
        try:
            locator_tuple = self._locator(locator)
            element = self._find(locator_tuple, timeout, "clickable")
            self._perform_click(element)
            self._wait(timeout).until(
                WaitForKeysVerification(locator_tuple, keys, click=False, element=element))
            self.driver.get(url)
        except Exception as err:
            self._fail(f"Failed to find element: {locator}, send keys: {keys!r} and go to {url}.", err)

    @_paced
    def click_element(self, element: WebElement, js_fallback: bool = True) -> None:
        """Scroll to, hover over and click an already located element."""
        try:
            self._perform_click(element, js_fallback)
        except Exception as err:
            self._fail(f"Failed to click element: {element}.", err)

    @_paced
    def try_to_click_element(self, element: WebElement) -> None:
        """Click ``element`` if it is truthy (a ``False``/None result from ``try_to_get_element`` is ignored)."""
        try:
            if element:
                self._perform_click(element)
        except Exception as err:
            self._fail(f"Failed to click element: {element}.", err)

    @_paced
    def try_click(self, locator: str, timeout: float | None = None) -> bool:
        """
        Click the element matching ``locator`` if it becomes clickable within ``timeout``.

        Never raises and never logs an error; use it for optional steps ("dismiss the banner if
        it is there"). ``timeout=0`` checks once.

        Returns:
            bool: True when the click happened.
        """
        try:
            self._do_with_element(locator, self._perform_click, timeout)
            return True
        except Exception as err:
            logger.debug("try_click(%s) skipped: %s", locator, err)
            return False

    @_paced
    def js_click(self, locator: Any, timeout: float | None = None) -> None:
        """Click through JavaScript (``element.click()``), which ignores overlays and visibility."""
        try:
            self._do_with_element(
                locator, lambda element: self._script("arguments[0].click();", element), timeout, "present")
        except Exception as err:
            self._fail(f"Failed to JavaScript-click {locator}.", err)

    @_paced
    def click_chain_elements_infinitely(
            self, locators: list, pause_time: int = 0, timeout: float | None = None) -> None:
        """Click each locator in turn, forever, sleeping ``pause_time`` after every round."""
        locator = None
        while True:
            try:
                for locator in locators:
                    self._do_with_element(locator, self._perform_click, timeout)
                sleep(pause_time)
            except Exception as err:
                self._fail(f"Failed to find element: {locator} and click.", err)

    @_paced
    def click_chain_elements(
            self, locators: list, pause_time: int = 0, loop_count: int = 10, timeout: float | None = None) -> None:
        """Click each locator in turn, ``loop_count`` rounds, sleeping ``pause_time`` after every round."""
        locator = None
        try:
            for _ in range(loop_count):
                for locator in locators:
                    self._do_with_element(locator, self._perform_click, timeout)
                sleep(pause_time)
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and click.", err)

    def _click_each(self, locator: str, timeout: float | None) -> int:
        """Click every visible, enabled element matching ``locator``; skips ones that go stale. Raises on other failures."""
        clicked = 0
        for element in self._find_all(locator, timeout, "enabled"):
            try:
                self._perform_click(element)
                clicked += 1
            except StaleElementReferenceException:
                continue
        return clicked

    @_paced
    def click_all_elements_and_scroll(
            self, locator: str, scroll_count=1, timeout: float | None = None) -> None:
        """Click every element matching ``locator`` then scroll to the bottom ``scroll_count`` times."""
        try:
            self._click_each(locator, timeout)
            self.scroll_to_bottom(scroll_count)
        except Exception as err:
            self._fail(f"Failed to find elements: {locator} and click.", err)

    @_paced
    def click_all_elements(self, locator: str, timeout: float | None = None) -> None:
        """Click every visible, enabled element matching ``locator``."""
        try:
            self._click_each(locator, timeout)
        except Exception as err:
            self._fail(f"Failed to find elements: {locator} and click.", err)

    @_paced
    def click_all_elements_and_reload(self, locator: str, timeout: float | None = None) -> None:
        """Click every element matching ``locator`` then reload the page."""
        try:
            self._click_each(locator, timeout)
            self.driver.refresh()
        except Exception as err:
            self._fail(f"Failed to find elements: {locator} and click.", err)

    @_paced
    def process_elements_until_none(self, locator: str, action: Callable[[WebElement], Any], limit: int | None = None,
                                    timeout: float | None = None, wait_for_removal: bool = True) -> int:
        """
        Apply ``action`` to the first element matching ``locator``, re-find, and repeat until
        nothing matches (the "delete every row" loop).

        Args:
            locator (str): The locator of the elements to process.
            action (callable): Called with the clickable element.
            limit (int, optional): Maximum number of elements to process; None for no limit.
            timeout (float, optional): Seconds to wait for each element, by default poll_time.
            wait_for_removal (bool): After each action wait until that element is gone (or no
                longer first) before re-finding, so a slow removal is not processed twice.

        Returns:
            int: How many elements were processed.
        """
        count = 0
        locator_tuple = self._locator(locator)
        try:
            while limit is None or count < limit:
                elements = self.driver.find_elements(*locator_tuple)
                if not elements:
                    break
                element = elements[0]
                try:
                    self._wait(timeout).until(EC.element_to_be_clickable(element))
                    action(element)
                except StaleElementReferenceException:
                    continue
                count += 1
                if wait_for_removal:
                    self._wait(timeout).until(
                        lambda driver: _is_stale(element)
                        or not (remaining := driver.find_elements(*locator_tuple))
                        or remaining[0] != element)
            return count
        except Exception as err:
            self._fail(f"Failed while processing elements: {locator} ({count} done).", err)
            return count

    def click_elements_until_none(self, locator: str, limit: int | None = None, timeout: float | None = None,
                                  wait_for_removal: bool = True) -> int:
        """Click the first element matching ``locator`` repeatedly until none is left; returns the count."""
        return self.process_elements_until_none(locator, self._perform_click, limit, timeout, wait_for_removal)

    @_paced
    def click_and_wait_for_load(self, locator: str, timeout: float | None = None) -> bool:
        """
        Click the element matching ``locator`` and wait until it is gone, disabled, or the page changed.

        Args:
            locator (str): The locator of the element to click.
            timeout (float, optional): Seconds to wait, by default poll_time.

        Returns:
            bool: True once the condition held, False on failure when throw is False.
        """
        try:
            self._wait(timeout).until(
                WaitForLoadAfterClick(self._locator(locator)))
            return True
        except Exception as err:
            self._fail(f"Failed to click {locator} and wait for load within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def click_and_wait_for_element(self, locator: str, locator2: str, timeout: float | None = None) -> bool:
        """
        Click the element matching ``locator`` and wait until an element matching ``locator2`` is present.

        Args:
            locator (str): The locator of the element to click.
            locator2 (str): The locator of the element that should appear afterwards.
            timeout (float, optional): Seconds to wait, by default poll_time.

        Returns:
            bool: True once the awaited element is present, False on failure when throw is False.
        """
        try:
            self._wait(timeout).until(
                WaitForElementAfterClick(self._locator(locator), self._locator(locator2)))
            return True
        except Exception as err:
            self._fail(f"Failed to click {locator} and find {locator2} within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def click_and_wait_for_html_load(self, locator: str, timeout: float | None = None) -> bool:
        """
        Click the element matching ``locator`` and wait until the HTML changed underneath it.

        Succeeds when the clicked element is removed or re-rendered, when nothing matches the locator
        any more, or when the whole page was replaced. For a guarantee that the browser actually left
        the page use ``click_and_wait_for_page_change``.

        Args:
            locator (str): The locator of the element to click.
            timeout (float, optional): Seconds to wait, by default poll_time.

        Returns:
            bool: True once the HTML changed, False on failure when throw is False.
        """
        try:
            self._wait(timeout).until(
                WaitForHtmlLoadAfterClick(self._locator(locator)))
            return True
        except Exception as err:
            self._fail(f"Failed to click {locator} and wait for the HTML to change within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def click_element_and_wait_for_load(self, element: WebElement, timeout: float | None = None) -> bool:
        """
        Click an already located element and wait until it is gone, disabled, or the page changed.

        The clickable wait and the load wait share one ``timeout`` budget.

        Args:
            element (WebElement): The element to click.
            timeout (float, optional): Seconds to wait, by default poll_time.

        Returns:
            bool: True once the condition held, False on failure when throw is False.
        """
        try:
            total = self._timeout(timeout)
            started = monotonic()
            self._wait(total).until(EC.element_to_be_clickable(element))
            remaining = max(total - (monotonic() - started), self.poll_frequency)
            self._wait(remaining).until(WaitForHtmlLoadAfterClickElement(element))
            return True
        except Exception as err:
            self._fail(f"Failed to click element and wait for load within {self._timeout(timeout)}s.", err)
            return False

    # ------------------------------------------------------------------ waits and existence checks

    def wait_for_element(self, locator: str, timeout: float | None = None) -> bool:
        """
        Wait until an element matching ``locator`` is present in the DOM.

        Returns:
            bool: True once the element is present, False on timeout when throw is False.
        """
        try:
            self._wait(timeout).until(
                EC.presence_of_element_located(self._locator(locator)))
            return True
        except Exception as err:
            self._fail(f"Timed out after {self._timeout(timeout)}s waiting for element: {locator}.", err)
            return False

    @_paced
    def wait_to_click_element(self, locator: str, wait: int = 1, timeout: float | None = None) -> None:
        """Retry clicking the element matching ``locator`` (each attempt waits up to ``wait`` seconds) until it succeeds."""
        try:
            self._wait(timeout).until(
                WaitElementToBeClickable(self._locator(locator), wait))
        except Exception as err:
            self._fail(f"Failed to find element: {locator} and click.", err)

    def wait_for_element_to_disappear_by_xpath(
            self, locator: str, wait: float | None = None, *, timeout: float | None = None) -> bool:
        """
        Wait until no element matches ``locator`` (it was removed from the DOM or never existed).

        Args:
            locator (str): The locator of the element that should disappear.
            wait (float, optional): Seconds to wait for it to disappear, by default poll_time.
                ``wait=0`` performs a single check. ``timeout`` is a keyword alias.

        Returns:
            bool: True once nothing matches, False on timeout when throw is False.
        """
        wait = timeout if wait is None else wait
        try:
            self._wait(wait).until(
                ElementIsAbsent(self._locator(locator)))
            return True
        except Exception as err:
            self._fail(f"Element did not disappear within {self._timeout(wait)}s: {locator}.", err)
            return False

    def wait_for_element_to_disappear(
            self, element: WebElement | tuple | str, wait: float | None = None, *, timeout: float | None = None) -> bool:
        """
        Wait until an element is gone.

        Args:
            element (WebElement | tuple | str): A WebElement (waits for it to become stale), a
                ``(By, value)`` tuple such as ``LocatedWebElement.get_locator()``, or a bare locator
                string (both wait until nothing matches the locator).
            wait (float, optional): Seconds to wait for it to disappear, by default poll_time.
                ``timeout`` is a keyword alias.

        Returns:
            bool: True once the element is gone, False on timeout when throw is False.
        """
        wait = timeout if wait is None else wait
        try:
            if isinstance(element, WebElement):
                condition = ElementIsStale(element)
            else:
                condition = ElementIsAbsent(self._locator(element))
            self._wait(wait).until(condition)
            return True
        except Exception as err:
            self._fail(f"Element did not disappear within {self._timeout(wait)}s: {element}.", err)
            return False

    def element_exists(self, locator: str, timeout: float | None = None) -> bool:
        """
        Check whether an element matching ``locator`` appears within the timeout. Never raises.

        Args:
            locator (str): The locator of the element to look for.
            timeout (float, optional): Seconds to wait for it to appear, by default poll_time.

        Returns:
            bool: True if the element is (or becomes) present, False otherwise.
        """
        try:
            return bool(
                self._wait(timeout).until(
                    EC.presence_of_element_located(self._locator(locator)))
            )
        except Exception:
            return False

    def element_does_not_exist(self, locator: str, timeout: float | None = None) -> bool:
        """
        Check whether no element matches ``locator`` (immediately or within the timeout). Never raises.

        This is the mirror of ``element_exists``: use it to confirm that an error banner, a login form
        or a spinner is not on the page before moving on.

        Args:
            locator (str): The locator of the element that should be absent.
            timeout (float, optional): Seconds to wait for it to disappear, by default poll_time.

        Returns:
            bool: True if nothing matches (or stops matching) within the timeout, False if it is still there.
        """
        try:
            return bool(
                self._wait(timeout).until(ElementIsAbsent(self._locator(locator)))
            )
        except Exception:
            return False

    def wait_for_visible(self, locator: str, timeout: float | None = None) -> bool:
        """Wait until the element matching ``locator`` is displayed."""
        try:
            self._find(locator, timeout, "visible")
            return True
        except Exception as err:
            self._fail(f"Element not visible within {self._timeout(timeout)}s: {locator}.", err)
            return False

    def wait_for_invisible(self, locator: str, timeout: float | None = None) -> bool:
        """Wait until the element matching ``locator`` is hidden or absent."""
        try:
            self._wait(timeout).until(EC.invisibility_of_element_located(self._locator(locator)))
            return True
        except Exception as err:
            self._fail(f"Element still visible after {self._timeout(timeout)}s: {locator}.", err)
            return False

    def wait_for_text(self, locator: str, text: str, timeout: float | None = None) -> bool:
        """Wait until the text of the element matching ``locator`` contains ``text``."""
        try:
            self._wait(timeout).until(EC.text_to_be_present_in_element(self._locator(locator), text))
            return True
        except Exception as err:
            self._fail(f"Text {text!r} did not appear in {locator} within {self._timeout(timeout)}s.", err)
            return False

    def wait_for_attribute(self, locator: str, attribute: str, value: str, timeout: float | None = None) -> bool:
        """Wait until ``attribute`` of the element matching ``locator`` equals ``value``."""
        locator_tuple = self._locator(locator)

        def condition(driver):
            try:
                return driver.find_element(*locator_tuple).get_attribute(attribute) == value
            except WebDriverException:
                return False

        try:
            self._wait(timeout).until(condition)
            return True
        except Exception as err:
            self._fail(f"Attribute {attribute} of {locator} did not become {value!r} within {self._timeout(timeout)}s.", err)
            return False

    def wait_for_url_contains(self, text: str, timeout: float | None = None) -> bool:
        """Wait until the current URL contains ``text``."""
        try:
            self._wait(timeout).until(EC.url_contains(text))
            return True
        except Exception as err:
            self._fail(f"URL did not contain {text!r} within {self._timeout(timeout)}s.", err)
            return False

    def wait_for_title_contains(self, text: str, timeout: float | None = None) -> bool:
        """Wait until the page title contains ``text``."""
        try:
            self._wait(timeout).until(EC.title_contains(text))
            return True
        except Exception as err:
            self._fail(f"Title did not contain {text!r} within {self._timeout(timeout)}s.", err)
            return False

    def wait_for_element_count(self, locator: str, count: int, timeout: float | None = None) -> bool:
        """Wait until exactly ``count`` elements match ``locator``."""
        locator_tuple = self._locator(locator)
        try:
            self._wait(timeout).until(lambda driver: len(driver.find_elements(*locator_tuple)) == count)
            return True
        except Exception as err:
            self._fail(f"{locator} did not reach {count} matches within {self._timeout(timeout)}s.", err)
            return False

    ## PAGE CHANGE FUNCTIONS ##

    def get_page_root(self) -> WebElement | None:
        """
        Return the current document's <html> element.

        Capture it (together with ``get_current_url()``) before an action that should navigate, then
        pass both to ``wait_for_page_change`` to block until that document has been replaced.

        Returns:
            WebElement | None: The root element, or None if it could not be captured.
        """
        try:
            return self.driver.find_element(By.TAG_NAME, "html")
        except Exception as err:
            return self._fail("Failed to capture the page root.", err)

    def get_current_url(self) -> str | None:
        """
        Return the current URL of the browsing context.

        Returns:
            str | None: The URL, or None if it could not be read.
        """
        try:
            return self.driver.current_url
        except Exception as err:
            return self._fail("Failed to read the current url.", err)

    def wait_for_page_change(self, old_root: WebElement | None, timeout: float | None = None,
                             old_url: str | None = None) -> bool:
        """
        Wait until the browser has left the page ``old_root`` / ``old_url`` were captured on.

        The page counts as changed once ``old_root`` is stale (the document was replaced) or the URL
        (ignoring any #fragment) differs from ``old_url``; the new document must then reach
        ``document.readyState == "complete"`` and stay put for one more poll so redirect chains settle.
        Use this after an action performed some other way, e.g. pressing Enter in a form.

        Args:
            old_root (WebElement | None): The <html> element from ``get_page_root()`` taken before the action.
            timeout (float, optional): Seconds to wait, by default poll_time.
            old_url (str, optional): The URL from ``get_current_url()`` taken before the action.

        Returns:
            bool: True once the page changed and loaded, False on timeout when throw is False.
        """
        try:
            self._wait(timeout).until(WaitForPageChange(old_root, old_url=old_url))
            return True
        except Exception as err:
            self._fail(f"Page did not change within {self._timeout(timeout)}s.", err)
            return False

    def wait_for_url_change(self, old_url: str, timeout: float | None = None) -> bool:
        """
        Wait until the current URL differs from ``old_url``.

        Returns:
            bool: True once the URL changed, False on timeout when throw is False.
        """
        try:
            self._wait(timeout).until(EC.url_changes(old_url))
            return True
        except Exception as err:
            self._fail(f"URL did not change from {old_url} within {self._timeout(timeout)}s.", err)
            return False

    @_paced
    def click_and_wait_for_page_change(self, locator: str, timeout: float | None = None) -> bool:
        """
        Click the element matching ``locator`` and wait until the browser has left the current page.

        The click is retried on every poll until it lands. Success means the document was replaced
        (full navigation, including inside the current iframe) or the URL changed (SPA navigation),
        the new page finished loading, and it stayed put for one more poll. A same-URL in-page update
        does not count: use ``click_and_wait_for_element`` or ``click_and_wait_for_html_load`` for
        those. A click that opens a new tab does not change the current page either: follow it with
        ``switch_to_latest_window``.

        Args:
            locator (str): The locator of the element to click.
            timeout (float, optional): Seconds to wait for the click and the page change, by default poll_time.

        Returns:
            bool: True once the new page is loaded, False on failure when throw is False.
        """
        condition = None
        try:
            condition = WaitForPageChangeAfterClick(locator=self._locator(locator))
            self._wait(timeout).until(condition)
            return True
        except Exception as err:
            if condition is not None and condition.clicked:
                message = f"Clicked {locator} but the page did not change within {self._timeout(timeout)}s."
            else:
                message = f"Failed to find and click {locator} within {self._timeout(timeout)}s."
            self._fail(message, err)
            return False

    @_paced
    def click_element_and_wait_for_page_change(self, element: WebElement, timeout: float | None = None) -> bool:
        """
        Click an already located element and wait until the browser has left the current page.

        See ``click_and_wait_for_page_change`` for what counts as a page change.

        Returns:
            bool: True once the new page is loaded, False on failure when throw is False.
        """
        condition = None
        try:
            condition = WaitForPageChangeAfterClick(element=element)
            self._wait(timeout).until(condition)
            return True
        except Exception as err:
            if condition is not None and condition.clicked:
                message = f"Clicked element but the page did not change within {self._timeout(timeout)}s."
            else:
                message = f"Failed to click element within {self._timeout(timeout)}s."
            self._fail(message, err)
            return False

    # ------------------------------------------------------------------ reading and writing the DOM

    def check_element_for_value_change(self, locator: str, forever=False, timeout: float | None = None) -> bool:
        """
        Wait until the text of the element matching ``locator`` changes from its first reading.

        With ``forever=True`` a timeout just keeps waiting (same baseline); other errors stop it.

        Returns:
            bool: True once the text changed, False on timeout when throw is False.
        """
        condition = WaitForValueToChange(self._locator(locator))
        while True:
            try:
                self._wait(timeout).until(condition)
                return True
            except TimeoutException as err:
                if forever:
                    continue
                self._fail(f"Value of {locator} did not change within {self._timeout(timeout)}s.", err)
                return False
            except Exception as err:
                self._fail(f"Failed while watching {locator} for a change.", err)
                return False

    def check_node_css_property(
            self, locator: str, property: str, search: str, value: str, return_value=False, timeout: float | None = None) -> Any:
        """
        Read a CSS property of the element matching ``locator`` and compare the part matched by
        the ``search`` regular expression (group 1 when present) with ``value``.

        Returns:
            With ``return_value=False``: True when it matches, False otherwise. With
            ``return_value=True``: the matched text when it matches, else the full property value.
            None on failure when throw is False.
        """
        try:
            element = self._find(locator, timeout, "present")
            element_property = element.value_of_css_property(property)
            match = re.search(search, element_property or "")
            if not match:
                return False
            match_str = match.group(1) if match.groups() else match.group(0)
            if match_str == value:
                return match_str if return_value else True
            return element_property if return_value else False
        except Exception as err:
            return self._fail(f"Failed to check css property {property} of {locator}.", err)

    def execute_script(self, script: str, return_value=True,
                       node: WebElement = None, args=()) -> Any:
        """
        Run JavaScript in the page.

        Args:
            script (str): The script; use ``return`` to hand a value back.
            return_value (bool): When False the result is discarded.
            node (WebElement, optional): Exposed to the script as ``arguments[0]``.
            args (iterable, optional): Further values exposed as ``arguments[1..]`` (or ``[0..]`` without ``node``).
        """
        try:
            script_args = ([node] if node is not None else []) + list(args or ())
            result = self.driver.execute_script(script, *script_args)
            return result if return_value else None
        except Exception as err:
            return self._fail("Failed to execute script.", err)

    def execute_async_script(self, script: str, return_value=True,
                             node: WebElement = None, args=()) -> Any:
        """Run asynchronous JavaScript (the script must call its last argument when done); see ``execute_script``."""
        try:
            script_args = ([node] if node is not None else []) + list(args or ())
            result = self.driver.execute_async_script(script, *script_args)
            return result if return_value else None
        except Exception as err:
            return self._fail("Failed to execute async script.", err)

    def get_text_from_node_convert(self, locator: str, ctype: Any, timeout: float | None = None) -> Any:
        """The text of the element matching ``locator`` converted with ``ctype`` (e.g. ``int``)."""
        try:
            element = self._find(locator, timeout, "visible")
            return ctype(element.text)
        except Exception as err:
            return self._fail(f"Failed to read and convert the text of {locator}.", err)

    def get_text_from_node(self, locator: str, timeout: float | None = None) -> str | None:
        """The visible text of the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "visible")
            return element.text
        except Exception as err:
            return self._fail(f"Failed to read the text of {locator}.", err)

    def get_text_from_node_element(self, element: WebElement, timeout: float | None = None) -> str | None:
        """The visible text of an already located element (waits for it to be displayed)."""
        try:
            element = self._find(element, timeout, "visible")
            return element.text
        except Exception as err:
            return self._fail("Failed to read the text of the element.", err)

    @_paced
    def set_attribute_of_node(
            self, locator: str, attribute: str, value: str, timeout: float | None = None) -> None:
        """Set ``attribute`` to ``value`` on the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            self._script("arguments[0].setAttribute(arguments[1], arguments[2]);", element, attribute, value)
        except Exception as err:
            self._fail(f"Failed to set attribute {attribute} on {locator}.", err)

    @_paced
    def remove_attribute_of_node(self, locator: str, attribute: str, timeout: float | None = None) -> None:
        """Remove ``attribute`` from the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            self._script("arguments[0].removeAttribute(arguments[1]);", element, attribute)
        except Exception as err:
            self._fail(f"Failed to remove attribute {attribute} from {locator}.", err)

    def get_property_from_node(self, locator: str, attr: str, timeout: float | None = None) -> Any:
        """A DOM property (``element.get_property``) of the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return element.get_property(attr)
        except Exception as err:
            return self._fail(f"Failed to read property {attr} of {locator}.", err)

    def get_attribute_from_node(self, locator: str, attr: str, timeout: float | None = None) -> Any:
        """An attribute (``element.get_attribute``) of the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return element.get_attribute(attr)
        except Exception as err:
            return self._fail(f"Failed to read attribute {attr} of {locator}.", err)

    def get_inner_html_from_node(self, locator: str, timeout: float | None = None) -> str | None:
        """The ``innerHTML`` of the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return element.get_attribute('innerHTML')
        except Exception as err:
            return self._fail(f"Failed to read the innerHTML of {locator}.", err)

    def get_outer_html_from_node(self, locator: str, timeout: float | None = None) -> str | None:
        """The ``outerHTML`` of the element matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return element.get_attribute('outerHTML')
        except Exception as err:
            return self._fail(f"Failed to read the outerHTML of {locator}.", err)

    def check_node_for_property(self, locator: str, property: str, timeout: float | None = None) -> bool | None:
        """Whether the DOM property ``property`` of the element matching ``locator`` is truthy."""
        try:
            element = self._find(locator, timeout, "present")
            return bool(element.get_property(property))
        except Exception as err:
            return self._fail(f"Failed to check property {property} of {locator}.", err)

    @_paced
    def select_option_from_dropdown(
            self, locator: str, select_type: DROPDOWNTYPE, value: Any, timeout: float | None = None) -> None:
        """Select an option of the ``<select>`` matching ``locator`` by index, value or visible text."""
        try:
            element = self._find(locator, timeout, "clickable")
            select = Select(element)
            if select_type == DROPDOWNTYPE.INDEX:
                select.select_by_index(value)
            elif select_type == DROPDOWNTYPE.VALUE:
                select.select_by_value(value)
            elif select_type == DROPDOWNTYPE.TEXT:
                select.select_by_visible_text(value)
            else:
                raise Error(f"Unknown DROPDOWNTYPE: {select_type}")
        except Exception as err:
            self._fail(f"Failed to select {value!r} in {locator}.", err)

    def get_dropdown_options(self, locator: str, timeout: float | None = None) -> list[str] | None:
        """The visible texts of all options of the ``<select>`` matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return [option.text for option in Select(element).options]
        except Exception as err:
            return self._fail(f"Failed to read the options of {locator}.", err)

    def get_selected_option(self, locator: str, timeout: float | None = None) -> str | None:
        """The visible text of the selected option of the ``<select>`` matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            return Select(element).first_selected_option.text
        except Exception as err:
            return self._fail(f"Failed to read the selected option of {locator}.", err)

    @_paced
    def upload_file(self, locator: str, path: str, timeout: float | None = None) -> None:
        """Send a local file path to the ``<input type="file">`` matching ``locator``."""
        try:
            element = self._find(locator, timeout, "present")
            element.send_keys(str(Path(path).resolve()))
        except Exception as err:
            self._fail(f"Failed to upload {path} through {locator}.", err)

    # ------------------------------------------------------------------ mouse

    def _element_for_action(self, target: Any, timeout: float | None, state: str = "visible") -> WebElement:
        return target if isinstance(target, WebElement) else self._find(target, timeout, state)

    @_paced
    def hover(self, target: Any, timeout: float | None = None) -> None:
        """Move the mouse over the element (locator or WebElement)."""
        try:
            element = self._element_for_action(target, timeout)
            self._pointer(element, lambda chain, _: chain,
                          "arguments[0].dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));")
        except Exception as err:
            self._fail(f"Failed to hover over {target}.", err)

    @_paced
    def double_click(self, target: Any, timeout: float | None = None) -> None:
        """Double-click the element (locator or WebElement)."""
        try:
            element = self._element_for_action(target, timeout, "clickable")
            self._pointer(element, lambda chain, el: chain.double_click(el),
                          "arguments[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));")
        except Exception as err:
            self._fail(f"Failed to double-click {target}.", err)

    @_paced
    def right_click(self, target: Any, timeout: float | None = None) -> None:
        """Right-click (context click) the element (locator or WebElement)."""
        try:
            element = self._element_for_action(target, timeout, "clickable")
            self._pointer(element, lambda chain, el: chain.context_click(el),
                          "arguments[0].dispatchEvent(new MouseEvent('contextmenu', {bubbles: true}));")
        except Exception as err:
            self._fail(f"Failed to right-click {target}.", err)

    @_paced
    def drag_and_drop(self, source: Any, target: Any, timeout: float | None = None) -> None:
        """Drag ``source`` onto ``target`` (locators or WebElements)."""
        try:
            source_element = self._element_for_action(source, timeout)
            target_element = self._element_for_action(target, timeout)
            ActionChains(self.driver).drag_and_drop(source_element, target_element).perform()
        except Exception as err:
            self._fail(f"Failed to drag {source} onto {target}.", err)

    # ------------------------------------------------------------------ screenshots

    def _save_png(self, png: bytes, path: str | None) -> bytes:
        if path:
            Path(path).write_bytes(png)
        return png

    def screenshot(self, path: str | None = None) -> bytes | None:
        """Screenshot of the viewport as PNG bytes; also written to ``path`` when given."""
        try:
            return self._save_png(self.driver.get_screenshot_as_png(), path)
        except Exception as err:
            return self._fail("Failed to take a screenshot.", err)

    def screenshot_element(self, target: Any, path: str | None = None, timeout: float | None = None) -> bytes | None:
        """Screenshot of one element as PNG bytes; also written to ``path`` when given."""
        try:
            element = self._element_for_action(target, timeout)
            return self._save_png(element.screenshot_as_png, path)
        except Exception as err:
            return self._fail(f"Failed to screenshot {target}.", err)

    def screenshot_full_page(self, path: str | None = None) -> bytes | None:
        """
        Screenshot of the whole page (not just the viewport) as PNG bytes.

        Firefox supports this natively; Chromium browsers use CDP; other drivers fall back to the viewport.
        """
        try:
            if hasattr(self.driver, "get_full_page_screenshot_as_png"):
                png = self.driver.get_full_page_screenshot_as_png()
            elif hasattr(self.driver, "execute_cdp_cmd"):
                metrics = self.driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
                size = metrics.get("cssContentSize") or metrics["contentSize"]
                result = self.driver.execute_cdp_cmd("Page.captureScreenshot", {
                    "captureBeyondViewport": True,
                    "clip": {"x": 0, "y": 0, "width": size["width"], "height": size["height"], "scale": 1},
                })
                png = base64.b64decode(result["data"])
            else:
                png = self.driver.get_screenshot_as_png()
            return self._save_png(png, path)
        except Exception as err:
            return self._fail("Failed to take a full-page screenshot.", err)

    # ------------------------------------------------------------------ alerts

    def wait_for_alert(self, timeout: float | None = None):
        """Wait for a JavaScript alert/confirm/prompt and return it (``selenium Alert``), or None."""
        try:
            return self._wait(timeout).until(EC.alert_is_present())
        except Exception as err:
            return self._fail(f"No alert appeared within {self._timeout(timeout)}s.", err)

    def get_alert_text(self, timeout: float | None = None) -> str | None:
        """The text of the open alert (waits for it), without closing it."""
        try:
            return self._wait(timeout).until(EC.alert_is_present()).text
        except Exception as err:
            return self._fail(f"No alert appeared within {self._timeout(timeout)}s.", err)

    @_paced
    def accept_alert(self, timeout: float | None = None) -> str | None:
        """Accept the open alert (waits for it) and return its text."""
        try:
            alert = self._wait(timeout).until(EC.alert_is_present())
            text = alert.text
            alert.accept()
            return text
        except Exception as err:
            return self._fail(f"Failed to accept an alert within {self._timeout(timeout)}s.", err)

    @_paced
    def dismiss_alert(self, timeout: float | None = None) -> str | None:
        """Dismiss the open alert (waits for it) and return its text."""
        try:
            alert = self._wait(timeout).until(EC.alert_is_present())
            text = alert.text
            alert.dismiss()
            return text
        except Exception as err:
            return self._fail(f"Failed to dismiss an alert within {self._timeout(timeout)}s.", err)

    @_paced
    def send_keys_to_alert(self, keys: str, accept: bool = True, timeout: float | None = None) -> str | None:
        """Type into the open prompt (waits for it), then accept (default) or dismiss it; returns its text."""
        try:
            alert = self._wait(timeout).until(EC.alert_is_present())
            text = alert.text
            alert.send_keys(keys)
            if accept:
                alert.accept()
            else:
                alert.dismiss()
            return text
        except Exception as err:
            return self._fail(f"Failed to answer a prompt within {self._timeout(timeout)}s.", err)

    # ------------------------------------------------------------------ logs and downloads

    def _get_log(self, kind: str) -> list:
        if not hasattr(self.driver, "get_log"):
            logger.debug("%s log is not available on this driver", kind)
            return []
        try:
            return list(self.driver.get_log(kind))
        except Exception as err:
            logger.debug("Could not read the %s log: %s", kind, err)
            return []

    def get_browser_logs(self) -> list:
        """Console log entries collected so far (Chromium drivers only; empty elsewhere). Reading clears them."""
        return self._get_log("browser")

    def get_performance_logs(self) -> list:
        """Performance (network/CDP) log entries; needs ``ChromeOptions(performance_logging=True)``. Empty elsewhere."""
        return self._get_log("performance")

    def wait_for_download(self, directory: str, timeout: float | None = None, pattern: str = "*", ignore=None) -> str | None:
        """
        Wait until a download in ``directory`` has finished.

        Finished means: a file matching ``pattern`` exists (not one of the names in ``ignore``) and
        no partial download (``.crdownload``, ``.part``, ``.tmp``, ``.download``) is left.

        Args:
            directory (str): The download directory.
            timeout (float, optional): Seconds to wait, by default poll_time.
            pattern (str): Glob pattern of the expected file name, by default any file.
            ignore (iterable, optional): File names that were already there (``os.listdir`` before the download).

        Returns:
            str | None: The path of the newest finished file, or None on timeout when throw is False.
        """
        folder = Path(directory)
        ignored = set(ignore or ())

        def finished(driver):
            if not folder.is_dir():
                return False
            if any(path.suffix.lower() in _PARTIAL_DOWNLOAD_SUFFIXES for path in folder.iterdir()):
                return False
            candidates = [
                path for path in folder.glob(pattern)
                if path.is_file() and path.name not in ignored
                and path.suffix.lower() not in _PARTIAL_DOWNLOAD_SUFFIXES
            ]
            if not candidates:
                return False
            return str(max(candidates, key=lambda path: path.stat().st_mtime))

        try:
            return self._wait(timeout).until(finished)
        except Exception as err:
            return self._fail(f"No finished download matching {pattern!r} in {directory} within {self._timeout(timeout)}s.", err)

    # ------------------------------------------------------------------ composite flows

    @_paced
    def login(self, username_locator: str, username: str, password_locator: str, password: str, submit_locator: str,
              success_locator: str | None = None, failure_locator: str | None = None, timeout: float | None = None) -> bool:
        """
        Fill a username/password form, submit it and report whether the login worked.

        After the submit click the method waits for the page to change (ignored when it does not,
        for single-page apps) and then polls until either ``failure_locator`` appears (-> False),
        ``success_locator`` appears (-> True), or, without ``success_locator``, the username field
        is gone (-> True). A timeout returns False. Element lookups honour ``throw``.

        Args:
            username_locator, password_locator, submit_locator (str): Locators of the form controls.
            username, password (str): The credentials to type.
            success_locator (str, optional): An element that only exists once logged in.
            failure_locator (str, optional): An error banner that means the credentials were rejected.
            timeout (float, optional): Seconds for each step, by default poll_time.
        """
        try:
            self.find_click_and_send_keys(username_locator, username, timeout=timeout)
            self.find_click_and_send_keys(password_locator, password, timeout=timeout)
            root, url = self.get_page_root(), self.get_current_url()
            self.find_and_click(submit_locator, timeout=timeout)
            with contextlib.suppress(TimeoutException):
                self._wait(timeout).until(WaitForPageChange(root, old_url=url))
            user_tuple = self._locator(username_locator)
            success_tuple = self._locator(success_locator) if success_locator else None
            failure_tuple = self._locator(failure_locator) if failure_locator else None

            def outcome(driver):
                if failure_tuple and driver.find_elements(*failure_tuple):
                    return "failure"
                if success_tuple is not None:
                    return "success" if driver.find_elements(*success_tuple) else False
                return "success" if not driver.find_elements(*user_tuple) else False

            try:
                result = self._wait(timeout).until(outcome)
            except TimeoutException:
                result = "timeout"
            if result != "success":
                logger.warning("login did not succeed (%s)", result)
            return result == "success"
        except Exception as err:
            self._fail("Login failed.", err)
            return False


class AppiumClient(DriverClient):

    def __init__(self, driver: DriverInterface, poll_time: int = 10, poll_frequency: float = 0.5, scroll_pause_time: int = 5, debug_mode: bool = False, throw: bool = False,
                 delete_profile: bool = False, close_previous_sessions: bool = False, action_delay: float = 0, disable_bot_detection_flag: bool = False, default_by=_APPIUM_DEFAULT_BY,
                 **kwargs) -> None:
        super().__init__(driver, poll_time, poll_frequency, scroll_pause_time, debug_mode, throw, delete_profile, close_previous_sessions, action_delay, disable_bot_detection_flag, default_by, **kwargs)
