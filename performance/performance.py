from ..driver.driverinterface import DriverInterface
from ..driver.client import DriverClient


class PerformanceClient(object):

    def __init__(self, client: DriverClient) -> None:
        self.client = client

    def measure(self) -> None:
        try:
            self.start = self.client.execute_script(
                "return window.performance.timing.navigationStart")
            self.loaded = self.client.execute_script(
                "return window.performance.timing.domContentLoadedEventEnd")
            self.ended = self.client.execute_script(
                "return window.performance.timing.loadEventEnd")
            self.backend_performance = self.loaded - self.start
            self.frontend_performance = self.ended - self.loaded
        except Exception as err:
            print(err)

    def measure_page(self, url: str) -> None:
        try:
            self.client.go(url)
            self.start = self.client.execute_script(
                "return window.performance.timing.navigationStart")
            self.loaded = self.client.execute_script(
                "return window.performance.timing.domContentLoadedEventEnd")
            self.ended = self.client.execute_script(
                "return window.performance.timing.loadEventEnd")
            self.page_backend_performance = self.loaded - self.start
            self.page_frontend_performance = self.ended - self.loaded
        except Exception as err:
            print(err)

    def getBackendPerformance(self):
        return self.backend_performance

    def getFrontPerformance(self):
        return self.frontend_performance

    def getPageBackendPerformance(self):
        return self.page_backend_performance

    def getPageFrontPerformance(self):
        return self.page_frontend_performance
