from pylibseleniummanagement.driver.options import *
from .services import BrowserService
from .options import BrowserOptions
try:
    import os
    from abc import ABC
    from selenium import webdriver
except ImportError as err:
    print("Unable to import: {}".format(err))
    exit()


class DriverInterface(ABC):
    def factory(self) -> object:
        """Factory function returns driver object"""


class Chrome(DriverInterface):

    def __init__(self, service: BrowserService, options: BrowserOptions) -> None:
        self.service = service
        self.options = options

    def factory(self) -> object:
        return webdriver.Chrome(service=self.service,
                                options=self.options)


class Firefox(DriverInterface):

    def __init__(self, service: BrowserService, options: BrowserOptions) -> None:
        self.service = service
        self.options = options

    def factory(self) -> object:
        try:
            return webdriver.Firefox(service=self.service, options=self.options)
        except Exception as err:
            print(f"HERE {err}")
            raise Exception(err)


class Safari(DriverInterface):

    def __init__(self, service: BrowserService, options: BrowserOptions) -> None:
        self.service = service
        self.options = options

    def factory(self) -> object:
        try:
            return webdriver.Safari(executable_path=self.executable_path, service_args=self.service_args)
        except Exception as err:
            print(err)
