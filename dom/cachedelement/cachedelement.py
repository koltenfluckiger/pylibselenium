import time

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class CachedElement:
    def __init__(self, driver_client, locator, max_retries=3, retry_delay=1):
        self.driver_client = driver_client
        self.locator = locator
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.element = None

    def get_element_dom(self):
        element = self.driver_client.driver.find_element(By.XPATH, self.locator)
        print(element)
        return element

    def locate(self):
        self.element = self.get_element_dom()

    def get_element(self):
        if not self.element:
            self.locate()
        return self.element

    def perform_action(self, action, *args, **kwargs):
        retries = 0
        while retries < self.max_retries:
            try:
                element = self.get_element()
                action(element, *args, **kwargs)
                return
            except StaleElementReferenceException:
                retries += 1
                self.element = None  # Clear the cached element
                time.sleep(self.retry_delay)

    def click(self):
        self.perform_action(lambda elem: elem.click())

    def send_keys(self, keys):
        self.perform_action(lambda elem, keys: elem.send_keys(keys), keys)
