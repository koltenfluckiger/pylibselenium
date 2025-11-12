from ..driver.driverinterface import DriverInterface

try:
    from typing import Any, List, Optional
    import pickle
    from datetime import datetime, timezone
    from pathlib import Path
    import sys
    import os
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


class ProfileClient(object):
    """
    Safer cookie loader/dumper:
      - Writes cookie file only if cookies look useful (fresh + likely auth)
      - Optionally navigates before loading so Selenium accepts domain
      - Stronger error handling and consistent return types
    """

    # names that often indicate auth/session cookies; tweak per site
    AUTH_COOKIE_HINTS = {"session", "auth", "sid", "ssid", "token", "jwt"}

    def __init__(self, driver: DriverInterface) -> None:
        self.driver = driver

    def __del__(self):
        try:
            self.driver = None
        except Exception as err:
            print(err)

    # ----------------- internal helpers -----------------

    def _resolved_path(self, path_str: str) -> Path:
        return Path(sys.path[0]).joinpath(Path(path_str)).resolve()

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

    # ----------------- public API -----------------

    def delete_cookie(self, name: str) -> None:
        try:
            self.driver.delete_cookie(name)
        except Exception as err:
            print(err)

    def delete_all_cookies(self) -> None:
        try:
            self.driver.delete_all_cookies()
        except Exception as err:
            print(err)

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
            tmp = resolved.with_suffix(resolved.suffix + ".tmp")

            with open(tmp, "wb") as f:
                pickle.dump(cookies, f)

            # atomic replace
            os.replace(tmp, resolved)
            return True
        except Exception as err:
            print(err)
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

            with open(resolved, "rb") as f:
                cookies = pickle.load(f)

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
                    c = self._coerce_expiry_int(dict(c))
                    self.driver.add_cookie(c)
                    loaded_any = True
                except Exception:
                    # bad cookie entry—skip the rest or continue? continue is safer
                    continue

            if loaded_any:
                # cause browser to send the cookies
                self.driver.refresh()
            return loaded_any
        except Exception:
            return False

    def get_cookie(self, name: str) -> Any:
        try:
            return self.driver.get_cookie(name)
        except Exception as err:
            print(err)

    def get_all_cookies(self) -> List:
        try:
            return self.driver.get_cookies()
        except Exception as err:
            print(err)

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
            print(err)
            return None

    def save_cookie(self, data: dict) -> None:
        try:
            self.driver.add_cookie(data)
        except Exception as err:
            print(err)

    def cookie_exists(self, name: str) -> bool:
        try:
            return bool(self.driver.get_cookie(name))
        except Exception as err:
            print(err)
            return False

    # ------------- added convenience methods -------------

    def cookie_file_looks_useful(self, path_str: str) -> bool:
        """Check if a cookie file exists, is readable, and passes usefulness heuristic."""
        try:
            resolved = self._resolved_path(path_str)
            if not resolved.exists() or resolved.stat().st_size == 0:
                return False
            with open(resolved, "rb") as f:
                cookies = pickle.load(f)
            return isinstance(cookies, list) and self._cookies_useful(cookies)
        except Exception:
            return False

    def current_cookies_look_useful(self) -> bool:
        """Check cookies already in the driver without writing them."""
        try:
            return self._cookies_useful(self.driver.get_cookies() or [])
        except Exception:
            return False
