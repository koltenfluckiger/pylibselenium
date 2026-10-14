import json
import logging
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional

from selenium.webdriver.common.by import By

from ..driver.client import DriverClient

logger = logging.getLogger(__name__)


class ProfileClient(object):
    """
    Safer cookie loader/dumper:
      - Writes cookie file only if cookies look useful (fresh + likely auth)
      - Optionally navigates before loading so Selenium accepts domain
      - Stronger error handling and consistent return types
      - ``.pkl`` files use pickle (compatible with older scripts and pylibzen); any other suffix is JSON
      - Accepts a raw WebDriver or a ``DriverClient``
    """

    # names that often indicate auth/session cookies; tweak per site
    AUTH_COOKIE_HINTS = {"session", "auth", "sid", "ssid", "token", "jwt"}

    def __init__(self, driver) -> None:
        """
        Parameters
        ----------
        driver : WebDriver | DriverClient
            The browser session. A ``DriverClient`` is accepted too; its ``.driver`` is used and
            ``ensure_session`` can then use ``element_exists`` for its check.
        """
        if isinstance(driver, DriverClient):
            self.client = driver
            self.driver = driver.driver
        else:
            self.client = None
            self.driver = driver

    # ----------------- internal helpers -----------------

    def _resolved_path(self, path_str: str) -> Path:
        """Relative paths are resolved against the running script's directory; absolute paths are used as given."""
        return Path(sys.path[0]).joinpath(Path(path_str)).resolve()

    @staticmethod
    def _uses_pickle(path: Path) -> bool:
        return path.suffix.lower() in (".pkl", ".pickle")

    def _read_cookie_file(self, path: Path) -> Any:
        if self._uses_pickle(path):
            with open(path, "rb") as f:
                return pickle.load(f)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # legacy pickle content under another suffix
            with open(path, "rb") as f:
                return pickle.load(f)

    def _write_cookie_file(self, path: Path, cookies: List[dict]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        if self._uses_pickle(path):
            with open(tmp, "wb") as f:
                pickle.dump(cookies, f)
        else:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2, sort_keys=True)
        # atomic replace
        os.replace(tmp, path)

    def _cookies_useful(self, cookies: List[dict]) -> bool:
        """Heuristic: has at least one non-expired cookie and one that looks auth-related."""
        if not cookies:
            return False
        now = datetime.now(timezone.utc).timestamp()

        def fresh(c):
            # No expiry => session cookie (fresh for this session)
            if "expiry" not in c:
                return True
            try:
                return float(c["expiry"]) > now
            except Exception:
                return False

        has_fresh = any(fresh(c) for c in cookies)
        looks_auth = any(
            any(h in str(c.get("name", "")).lower() for h in self.AUTH_COOKIE_HINTS)
            for c in cookies
        )
        # Require at least freshness; prefer also "looks auth"
        return has_fresh and looks_auth

    def _coerce_expiry_int(self, c: dict) -> dict:
        if "expiry" in c and isinstance(c["expiry"], float):
            try:
                c["expiry"] = int(c["expiry"])
            except Exception:
                # if it can't be coerced, drop it to avoid Selenium errors
                c.pop("expiry", None)
        return c

    def _sanitize_cookie(self, c: dict) -> dict:
        """
        Make a cookie dumped by one browser acceptable to ``add_cookie`` again.

        Firefox reports ``sameSite: "None"`` for cookies that never had the attribute and then
        rejects re-adding them without ``secure``; an unknown ``sameSite`` value is dropped too.
        """
        c = self._coerce_expiry_int(c)
        same_site = c.get("sameSite")
        if same_site is not None:
            if same_site not in ("Strict", "Lax", "None") or (same_site == "None" and not c.get("secure")):
                c.pop("sameSite", None)
        return c

    def _element_present(self, locator: str, timeout: Optional[float]) -> bool:
        if self.client is not None:
            return self.client.element_exists(locator, timeout=timeout)
        try:
            return bool(self.driver.find_elements(By.XPATH, locator))
        except Exception:
            return False

    # ----------------- public API -----------------

    def delete_cookie(self, name: str) -> None:
        try:
            self.driver.delete_cookie(name)
        except Exception as err:
            logger.error("Failed to delete cookie %s: %s", name, err)

    def delete_all_cookies(self) -> None:
        try:
            self.driver.delete_all_cookies()
        except Exception as err:
            logger.error("Failed to delete cookies: %s", err)

    def dump_cookies_to_file(self, path_str: str, require_useful: bool = True) -> bool:
        """
        Write cookies to file. If require_useful=True, only writes when cookies look useful
        (prevents empty/useless dumps). Returns True if a file was written.
        """
        try:
            cookies = self.driver.get_cookies() or []
            if require_useful and not self._cookies_useful(cookies):
                return False

            resolved = self._resolved_path(path_str)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self._write_cookie_file(resolved, cookies)
            return True
        except Exception as err:
            logger.error("Failed to write cookies to %s: %s", path_str, err)
            return False

    def load_cookies_from_file(
        self,
        path_str: str,
        base_url: Optional[str] = None,
        clear_first: bool = True,
    ) -> bool:
        """
        Load cookies from a file. If base_url is provided, navigates there first
        so Selenium accepts the domain. Returns True if cookies were loaded.
        """
        try:
            resolved = self._resolved_path(path_str)
            if not resolved.exists() or resolved.stat().st_size == 0:
                return False

            cookies = self._read_cookie_file(resolved)

            if not isinstance(cookies, list):
                return False

            if not self._cookies_useful(cookies):
                # file exists but contents are stale/useless; do not load
                return False

            if base_url:
                # must be on the right domain to add cookies
                self.driver.get(base_url)

            if clear_first:
                self.driver.delete_all_cookies()

            loaded_any = False
            for c in cookies:
                try:
                    c = self._sanitize_cookie(dict(c))
                    self.driver.add_cookie(c)
                    loaded_any = True
                except Exception as err:
                    # bad cookie entry: skip it and keep going
                    logger.debug("Skipping cookie %s: %s", c.get("name"), err)
                    continue

            if loaded_any:
                # cause browser to send the cookies
                self.driver.refresh()
            return loaded_any
        except Exception as err:
            logger.error("Failed to load cookies from %s: %s", path_str, err)
            return False

    def ensure_session(
        self,
        cookie_file: str,
        login: Callable[[], Any],
        base_url: Optional[str] = None,
        check_locator: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Restore a logged-in session from ``cookie_file`` or log in and save the cookies.

        1. If the file holds useful cookies they are loaded (after navigating to ``base_url`` when given).
        2. With ``check_locator`` the session only counts as valid when that element is present
           (an XPath, or any locator the wrapped ``DriverClient`` understands); without it,
           loading useful cookies is enough.
        3. Otherwise ``login()`` is called; unless it returns False (or the check fails) the
           cookies are dumped to ``cookie_file``.

        Returns:
            bool: True when a session is in place.
        """
        try:
            if self.load_cookies_from_file(cookie_file, base_url=base_url):
                if check_locator is None or self._element_present(check_locator, timeout):
                    return True
                logger.info("Saved cookies did not restore the session; logging in")
            elif base_url:
                self.driver.get(base_url)
            if login() is False:
                return False
            if check_locator is not None and not self._element_present(check_locator, timeout):
                return False
            self.dump_cookies_to_file(cookie_file)
            return True
        except Exception as err:
            logger.error("ensure_session failed: %s", err)
            return False

    def get_cookie(self, name: str) -> Any:
        try:
            return self.driver.get_cookie(name)
        except Exception as err:
            logger.error("Failed to read cookie %s: %s", name, err)

    def get_all_cookies(self) -> List:
        try:
            return self.driver.get_cookies()
        except Exception as err:
            logger.error("Failed to read cookies: %s", err)

    def check_cookie_for_expiration(self, name: str) -> Optional[bool]:
        """
        Returns True if the named cookie is expired, False if not expired,
        or None if the cookie is missing or unreadable.
        """
        try:
            c = self.driver.get_cookie(name)
            if not c:
                return None
            if "expiry" not in c:
                # session cookie: valid for the life of the session
                return False
            exp = float(c["expiry"])
            now = datetime.now(timezone.utc).timestamp()
            return exp <= now
        except Exception as err:
            logger.error("Failed to check cookie %s: %s", name, err)
            return None

    def save_cookie(self, data: dict) -> None:
        try:
            self.driver.add_cookie(data)
        except Exception as err:
            logger.error("Failed to add cookie: %s", err)

    def cookie_exists(self, name: str) -> bool:
        try:
            return bool(self.driver.get_cookie(name))
        except Exception as err:
            logger.error("Failed to read cookie %s: %s", name, err)
            return False

    # ------------- added convenience methods -------------

    def cookie_file_looks_useful(self, path_str: str) -> bool:
        """Check if a cookie file exists, is readable, and passes usefulness heuristic."""
        try:
            resolved = self._resolved_path(path_str)
            if not resolved.exists() or resolved.stat().st_size == 0:
                return False
            cookies = self._read_cookie_file(resolved)
            return isinstance(cookies, list) and self._cookies_useful(cookies)
        except Exception:
            return False

    def current_cookies_look_useful(self) -> bool:
        """Check cookies already in the driver without writing them."""
        try:
            return self._cookies_useful(self.driver.get_cookies() or [])
        except Exception:
            return False
