"""Driver service wrappers: the driver process that speaks WebDriver to the browser."""
import logging
import os
import tempfile
from abc import ABC
from typing import IO, Any

from selenium.webdriver.chrome.service import Service as CS
from selenium.webdriver.edge.service import Service as ES
from selenium.webdriver.firefox.service import Service as FS
from selenium.webdriver.safari.service import Service as SS

logger = logging.getLogger(__name__)


def default_log_path(name: str) -> str:
    """A log file path under the system temp directory, for callers that want driver logs."""
    return os.path.join(tempfile.gettempdir(), f"{name}.log")


def _resolve_log_output(log_output, log_path):
    """
    Combine Selenium 4's ``log_output`` with the deprecated ``log_path`` alias.

    Selenium 4.47 opens a string ``log_output`` as soon as the service is constructed, so a path
    whose directory does not exist (the historical ``None/chromeservice.log`` default) is dropped
    with a warning instead of failing driver start-up.
    """
    if log_output is not None:
        return log_output
    if log_path is None:
        return None
    parent = os.path.dirname(os.path.abspath(str(log_path)))
    if os.path.isdir(parent):
        return str(log_path)
    logger.warning("Ignoring log_path %s: directory %s does not exist", log_path, parent)
    return None


def _usable_executable(executable_path):
    """
    Return ``executable_path`` when it points at a real file, otherwise ``None``.

    ``None`` lets Selenium Manager (bundled with Selenium 4.6+) download a driver that matches the
    installed browser. The literal string ``"None"`` is treated as unset because several scripts
    build the path with ``"{}".format(os.getenv(...))``.
    """
    if not executable_path or str(executable_path) == "None":
        return None
    if os.path.isfile(str(executable_path)):
        return str(executable_path)
    logger.warning("Driver executable %s not found; letting Selenium Manager resolve it", executable_path)
    return None


class BrowserService(ABC):

    def factory(self) -> object:
        "Factory function returning service object"


class ChromeService(BrowserService):

    def __init__(
        self,
        executable_path: str | None = None,
        log_output: str | int | IO[Any] | None = None,
        *,
        log_path: str | None = None,
    ):
        """
        Parameters
        ----------
        executable_path : str, optional
            Path to chromedriver. ``None`` (default) lets Selenium Manager resolve a matching driver.
        log_output : str | int | IO, optional
            Where the driver writes its log (a file path, ``subprocess.STDOUT`` or a stream).
        log_path : str, optional
            Deprecated alias of ``log_output`` kept for existing callers.
        """
        self.executable_path = executable_path
        self.log_path = log_path
        self.log_output = _resolve_log_output(log_output, log_path)

    def factory(self) -> CS:
        return CS(executable_path=_usable_executable(self.executable_path), log_output=self.log_output)


class EdgeService(BrowserService):

    def __init__(
        self,
        executable_path: str | None = None,
        log_output: str | int | IO[Any] | None = None,
        *,
        log_path: str | None = None,
    ):
        self.executable_path = executable_path
        self.log_path = log_path
        self.log_output = _resolve_log_output(log_output, log_path)

    def factory(self) -> ES:
        return ES(executable_path=_usable_executable(self.executable_path), log_output=self.log_output)


class FirefoxService(BrowserService):

    def __init__(
        self,
        executable_path: str | None = None,
        log_output: str | int | IO[Any] | None = None,
        *,
        log_path: str | None = None,
    ):
        self.executable_path = executable_path
        self.log_path = log_path
        self.log_output = _resolve_log_output(log_output, log_path)

    def factory(self) -> FS:
        return FS(executable_path=_usable_executable(self.executable_path), log_output=self.log_output)


class SafariService(BrowserService):

    def __init__(
        self,
        executable_path: str | None = None,
        log_path: str | None = None,
        quiet: bool = False,
    ):
        """
        ``log_path`` is accepted for compatibility but safaridriver only supports toggling
        logging on or off; ``quiet=False`` enables it.
        """
        self.executable_path = executable_path
        self.log_path = log_path
        self.quiet = quiet

    def factory(self) -> SS:
        kwargs = {"enable_logging": not self.quiet}
        path = _usable_executable(self.executable_path)
        if path:
            kwargs["executable_path"] = path
        return SS(**kwargs)
