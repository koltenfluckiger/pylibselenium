import logging
import time

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class CachedElement:
    """
    A lazily located element that re-locates itself when the DOM re-renders.

    ``perform_action`` retries the action after a ``StaleElementReferenceException`` up to
    ``max_retries`` times, re-finding the element each time, and returns the action's result.
    When every attempt fails the last error is raised if the client was built with
    ``throw=True``; otherwise ``None`` is returned.
    """

    def __init__(self, driver_client, locator, max_retries=3, retry_delay=1, by=None):
        self.driver_client = driver_client
        self.locator = locator
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.by = by if by is not None else getattr(driver_client, "default_by", By.XPATH)
        self.element = None

    def get_element_dom(self):
        element = self.driver_client.driver.find_element(self.by, self.locator)
        logger.debug("Located %s=%s -> %s", self.by, self.locator, element)
        return element

    def locate(self):
        self.element = self.get_element_dom()

    def get_element(self):
        if not self.element:
            self.locate()
        return self.element

    def perform_action(self, action, *args, **kwargs):
        retries = 0
        last_error = None
        while retries < self.max_retries:
            try:
                return action(self.get_element(), *args, **kwargs)
            except StaleElementReferenceException as err:
                last_error = err
                retries += 1
                self.element = None  # Clear the cached element
                time.sleep(self.retry_delay)
        logger.error("Action on %s=%s still failing after %s retries", self.by, self.locator, self.max_retries)
        if getattr(self.driver_client, "throw", False) and last_error is not None:
            raise last_error
        return None

    def click(self):
        return self.perform_action(lambda elem: elem.click())

    def send_keys(self, keys):
        return self.perform_action(lambda elem, keys: elem.send_keys(keys), keys)

    def text(self):
        return self.perform_action(lambda elem: elem.text)
