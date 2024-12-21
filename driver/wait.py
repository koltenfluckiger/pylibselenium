import logging
import random
from time import sleep

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Set up logging
logging.basicConfig(level=logging.ERROR)


class PresenceOfAllElementsLocatedIfNotEmpty:
    """Check if elements located by the locator are present and not empty."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            elements = driver.find_elements(*self.locator)
            return elements or False
        except Exception as err:
            return False


class WaitForElementToBeStale:
    """Wait for an element located by the locator to become stale."""

    def __init__(self, locator, wait):
        self.locator = locator
        self.wait = wait

    def __call__(self, driver):
        try:
            driver.find_element(*self.locator)
            sleep(self.wait)
            return False
        except Exception as err:
            return True


class WindowHandleToBeAvailable:
    """Check if a window handle at a specific index is available."""

    def __init__(self, index):
        self.index = index

    def __call__(self, driver):
        try:
            return driver.window_handles[self.index]
        except IndexError:
            return False
        except Exception as err:
            return False


class WaitForElementReadyState:
    """Check if an element located by the locator is in a ready state."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            ready_state = driver.execute_script("return document.readyState")
            return element if ready_state == "complete" else False
        except Exception as err:
            return False


class WindowHandleToBeAvailableSwitchClosePrevious:
    """Switch to a window handle and close the previous one."""

    def __init__(self, index):
        self.index = index

    def __call__(self, driver):
        try:
            window_handle = driver.window_handles[self.index]
            previous_window_handle = driver.window_handles[self.index - 1]
            driver.close()
            driver.switch_to.window(window_handle)
            return True
        except IndexError:
            return False
        except Exception as err:
            return False


class WaitElementToBeClickable:
    """Wait for an element located by the locator to be clickable and click it."""

    def __init__(self, locator, wait):
        self.locator = locator
        self.wait = wait

    def __call__(self, driver):
        try:
            sleep(self.wait)
            element = WebDriverWait(driver, self.wait).until(EC.element_to_be_clickable(self.locator))
            element.click()
            return True
        except Exception as err:
            return False


class WaitForValueToChange:
    """Wait for the value of an element located by the locator to change."""

    def __init__(self, locator):
        self.locator = locator
        self.previous_text = None

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            if self.previous_text is None:
                self.previous_text = element.text
                return False
            return self.previous_text != element.text
        except Exception as err:
            return False


class WaitForElementToBeRemoved:

    def __init__(self, element):
        self.element = element

    def __call__(self, driver):
        try:
            WebDriverWait(driver, 10).until(EC.staleness_of(self.element))
            return True
        except:
            return False


class WaitForHtmlLoadAfterClick:
    """Wait for the HTML to load after an element located by the locator is clicked."""

    def __init__(self, locator):
        self.locator = locator
        self.clicked = False

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            if not self.clicked:
                element.click()
                self.clicked = True
                return False
            return False
        except Exception as err:
            return True


class WaitForHtmlLoadAfterClickElement:
    """Wait for the HTML to load after a specific element is clicked."""

    def __init__(self, element):
        self.element = element
        self.clicked = False

    def __call__(self, driver):
        try:
            if not self.clicked:
                self.element.click()
                self.clicked = True
                return False
            return not self.element.is_enabled()
        except Exception as err:
            return False


class WaitForLoadAfterClick:
    """Wait for an element to load after being clicked."""

    def __init__(self, locator):
        self.locator = locator
        self.clicked = False

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            if not self.clicked:
                element.click()
                self.clicked = True
                return False
            return not element.is_enabled()
        except Exception as err:
            return True


class WaitForLoadAfter:
    """Wait for an element to load."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            return not element.is_enabled()
        except Exception as err:
            return False


class WaitForElementAfterClick:
    """Wait for an element to appear after clicking another element."""

    def __init__(self, locator, waited_locator):
        self.locator = locator
        self.waited_locator = waited_locator
        self.clicked = False

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            if not self.clicked:
                element.click()
                self.clicked = True
            waited_element = driver.find_element(*self.waited_locator)
            return bool(waited_element)
        except Exception as err:
            return False


class WaitForKeysVerification:
    """Wait for keys to be sent to an element and verify."""

    def __init__(self, locator, keys):
        self.locator = locator
        self.keys = str(keys)

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            element.click()
            element.clear()
            element.send_keys(self.keys)
            value = str(element.get_property("value"))
            return value == self.keys
        except Exception as err:
            return False


class WaitForKeysVerificationWithDelay:
    """Wait for keys to be sent to an element with a delay and verify."""

    def __init__(self, locator, keys, delay):
        self.locator = locator
        self.keys = keys
        self.delay = delay

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            element.click()
            element.clear()
            action = ActionChains(driver)
            for key in self.keys:
                action.key_down(key)
                action.pause(random.uniform(0, self.delay) / 1000)
                action.key_up(key)
                action.perform()
            value = str(element.get_property("value"))
            return value == self.keys
        except Exception as err:
            return False
