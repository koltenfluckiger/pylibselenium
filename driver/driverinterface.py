from pylibseleniummanagement.driver.options import *
from .services import BrowserService
from .options import BrowserOptions
import traceback
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
        try:
            return webdriver.Chrome(service=self.service,
                                    options=self.options)
        except Exception as err:
            traceback.print_exc()



class Firefox(DriverInterface):

    def __init__(self, service: BrowserService, options: BrowserOptions) -> None:
        self.service = service
        self.options = options

    def factory(self) -> object:
        try:
            return webdriver.Firefox(service=self.service, options=self.options)
        except Exception as err:
            traceback.print_exc()


class Safari(DriverInterface):

    def __init__(self, service: BrowserService, options: BrowserOptions) -> None:
        self.service = service
        self.options = options

    def factory(self) -> object:
        try:
            return webdriver.Safari(executable_path=self.executable_path, service_args=self.service_args)
        except Exception as err:
            traceback.print_exc()

class RemoteWebdriver(DriverInterface):
    
    def __init__(self, remote_url: str, options: BrowserOptions) -> None:
        self.remote_url = remote_url
        self.options = options

    def factory(self) -> object:
        try:
            return webdriver.Remote(command_executor=self.remote_url, options=self.options)
        except Exception as err:
            traceback.print_exc()
