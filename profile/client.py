from ..driver.driverinterface import DriverInterface

try:
    from typing import Any, List
    import pickle
    from datetime import datetime
    from pathlib import Path
    import sys
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


class ProfileClient(object):

    def __init__(self, driver: DriverInterface) -> None:
        self.driver = driver

    def __del__(self):
        try:
            self.driver=None
        except Exception as err:
            print(err)

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

    def dump_cookies_to_file(self, dir: str) -> None:
        try:
            resolved_dir = Path(sys.path[0]).joinpath(Path(dir)).resolve()
            with open(resolved_dir, "wb") as cookie:
                pickle.dump(self.driver.get_cookies(), cookie)
        except Exception as err:
            print(err)

    def load_cookies_from_file(self, dir: str) -> None:
        try:
            resolved_dir = Path(sys.path[0]).joinpath(Path(dir)).resolve()
            with open(resolved_dir, "rb") as cookies:
                l_cookies = pickle.load(cookies)
                for cookie in l_cookies:
                    self.driver.add_cookie(cookie)
            self.driver.refresh()
            return True
        except Exception as err:
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

    def check_cookie_for_expiration(self, cookie: str) -> bool:
        try:
            now = datetime.now()
            cookie = self.driver.get_cookie(cookie)
            expiration = cookie['expiry']
            expiration_date = datetime.fromtimestamp(cookie['expiry'])
            if expiration_date < now:
                return True
            else:
                return False
        except Exception as err:
            print(err)

    def save_cookie(self, data: dict) -> None:
        try:
            self.driver.add_cookie(data)
        except Exception as err:
            print(err)

    def cookie_exists(self, name: str) -> bool:
        try:
            cookie = self.driver.get_cookie(name)
            if cookie:
                return True
            else:
                return False
        except Exception as err:
            print(err)
