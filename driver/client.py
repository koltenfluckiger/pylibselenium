import contextlib
import traceback

from .delayer import DelayerMetaClass, delayed_function
from .driverinterface import DriverInterface
from .types import DROPDOWNTYPE, MODIFERKEYS
from .wait import *

try:
    import logging
    import os
    import pathlib
    import re
    import shutil
    from enum import Enum
    from pathlib import Path
    from platform import platform
    from time import sleep
    from typing import Any

    import psutil
    from psutil import Process
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError as err:
    print(f"Unable to import: {err}")
    exit()

TEMP_DIR = pathlib.Path(
    os.getenv("TEMP") or "/tmp").joinpath("pylibseleniummanagement.log").resolve()
logging.basicConfig(filename=TEMP_DIR)


class Error(Exception):
    def __init__(self, text):
        self.text = text


class DriverClient(object):

    def __init__(self, driver: DriverInterface, poll_time: int = 10, poll_frequency: int = 1, scroll_pause_time: int = 5, debug_mode: bool = False, throw: bool = False,
                 delete_profile: bool = False, close_previous_sessions: bool = False, action_delay: int = 0, disable_bot_detection_flag: bool = False) -> None:
        """
        A client to interact with and manipulate web pages using Selenium.

        Parameters
        ----------
        driver : DriverInterface
            A Selenium WebDriver instance to interface with the browser.
        poll_time : int, optional
            Maximum time, in seconds, that the driver should wait when trying to find an element or elements if they are not immediately available, by default 10.
        poll_frequency : int, optional
            Sleep interval between calls, in seconds, by default 1.
        scroll_pause_time : int, optional
            Pause time, in seconds, between scroll actions, by default 5.
        debug_mode : bool, optional
            If True, the driver won't quit when the instance is deleted, by default False.
        throw : bool, optional
            If True, the class will raise exceptions, otherwise, it will only log them, by default False.
        delete_profile : bool, optional
            If True, the user profile used during the session will be deleted upon closing the driver, by default False.
        close_previous_sessions : bool, optional
            If True, previous sessions will be closed upon starting a new one, by default False.
        action_delay : int, optional
            A delay, in seconds, to wait between consecutive actions, by default 0.
        disable_bot_detection_flag : bool, optional
            If True, executes various commands to obfuscate the webdriver, by default False.

        Attributes
        ----------
        close_previous_sessions : bool
            If True, previous sessions will be closed upon starting a new one.
        debug_mode : bool
            If True, the driver won't quit when the instance is deleted.
        delete_profile : bool
            If True, the user profile used during the session will be deleted upon closing the driver.
        driver : DriverInterface
            A Selenium WebDriver instance to interface with the browser.
        poll_frequency : int
            Sleep interval between calls, in seconds.
        poll_time : int
            Maximum time, in seconds, that the driver should wait when trying to find an element or elements if they are not immediately available.
        scroll_pause_time : int
            Pause time, in seconds, between scroll actions.
        throw : bool
            If True, the class will raise exceptions, otherwise, it will only log them.
        action_delay : int
            A delay, in seconds, to wait between consecutive actions.
        disable_bot_detection_flag : bool
            If True, executes various commands to obfuscate the webdriver.
        """
        self.close_previous_sessions = close_previous_sessions
        self.debug_mode = debug_mode
        self.delete_profile = delete_profile
        self.driver = driver
        self.poll_frequency = poll_frequency
        self.poll_time = poll_time
        self.scroll_pause_time = scroll_pause_time
        self.throw = throw
        self.action_delay = action_delay
        self.disable_bot_detection_flag = disable_bot_detection_flag
        self.__setup()
    def __del__(self) -> None:

        with contextlib.suppress(Exception):
            if self.debug_mode == False:
                self.driver.quit()
                self._kill_processes()
                self.driver = None

    def _kill_processes(self):
        """
        Kill all processes associated with the driver's service.

        This method attempts to terminate all child processes spawned by the driver's service.
        It does not raise exceptions but logs them if they occur.
        """
        with contextlib.suppress(Exception):
            if self.driver.service.process.pid:
                pid = self.driver.service.process.pid
                p = psutil.Process(pid)
                children = p.children(recursive=True)
                children.append(p)
                for process in children:
                    with contextlib.suppress(Exception):
                        process.kill()

    def _delete_profile(self):
        with contextlib.suppress(Exception):
            browser_name = self.driver.capabilities['browserName']
            if browser_name == 'chrome':
                data_dir = self.driver.capabilities['chrome']['userDataDir']
            elif browser_name == 'firefox':
                data_dir = self.driver.capabilities['moz:profile']
            shutil.rmtree(Path(data_dir).resolve())
    def __setup(self):
        try:
            os_platform = {
                "windows": "Win32",
                "linux": "MacIntel"
            }
            current_os = os_platform['windows'] if 'windows' in platform(
            ) else os_platform['linux']
            if self.disable_bot_detection_flag:
                self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                    "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.53 Safari/537.36'})
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: ()=> false}), Object.defineProperty(navigator,'languages', {get: ()=> ['en-US', 'en']}), Object.defineProperty(navigator, 'platform', {get: () =>'MacIntel'}), Object.defineProperty(navigator, 'deviceMemory', {get: () => 8})"})
                self.driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})")
                self.driver.execute_script("""
                var inject = function () {
                var overwrite = function (name) {
                const OLD = HTMLCanvasElement.prototype[name];
                Object.defineProperty(HTMLCanvasElement.prototype, name, {
                    "value": function () {
                    var shift = {
                        'r': Math.floor(Math.random() * 10) - 5,
                        'g': Math.floor(Math.random() * 10) - 5,
                        'b': Math.floor(Math.random() * 10) - 5,
                        'a': Math.floor(Math.random() * 10) - 5
                    };
                    var width = this.width, height = this.height, context = this.getContext("2d");
                    var imageData = context.getImageData(0, 0, width, height);
                    for (var i = 0; i < height; i++) {
                        for (var j = 0; j < width; j++) {
                        var n = ((i * (width * 4)) + (j * 4));
                        imageData.data[n + \
                            0] = imageData.data[n + 0] + shift.r;
                        imageData.data[n + \
                            1] = imageData.data[n + 1] + shift.g;
                        imageData.data[n + \
                            2] = imageData.data[n + 2] + shift.b;
                        imageData.data[n + \
                            3] = imageData.data[n + 3] + shift.a;
                        }
                    }
                    context.putImageData(imageData, 0, 0);
                    return OLD.apply(this, arguments);
                    }
                });
                };
                overwrite('toBlob');
                overwrite('toDataURL');
            };
            inject();
                """)
        except Exception as err:
            print(err)

    def check_throw(self, error: Error) -> None:
        logging.critical(error)
        traceback.print_exc(error)
        if self.throw:
            raise error
        else:
            pass

    def maximize_window(self):
        """
        Maximize the current browser window.

        Raises:
            Error
                If an error occurs while maximizing the window.

        Returns:
            None
        """
        try:
            self.driver.maximize_window()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def close(self) -> None:
        """
        Close the current browser window.

        Raises:
            Error
                If an error occurs while closing the window.

        Returns:
            None
        """

        try:
            self.driver.close()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def quit(self) -> None:
        """
        Quits the driver session.

        Raises:
            Error: If an exception occurs during the driver quitting process.
        """
        try:
            self.driver.quit()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def go(self, url: str) -> None:
        """
        Navigates the driver to the specified URL.

        Args:
            url (str): The URL to navigate to.

        Raises:
            Error: If an exception occurs during the navigation process.
        """

        try:
            self.driver.get(url)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def reload(self) -> None:
        """
        Reloads the current page in the driver session.

        Raises:
            Error: If an exception occurs during the page reloading process.
        """

        try:
            self.driver.refresh()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def scroll_to_top(self) -> None:
        """
        Refreshes the current page in the driver session.

        Raises:
            Error: If an exception occurs during the page refreshing process.
        """

        try:
            self.execute_script("window.scrollTo(0, 0);")
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def scroll_to_bottom(self, times: int) -> None:
        """
        Scrolls to the bottom of the page a specified number of times.

        Args:
            times (int): The number of times to scroll to the bottom of the page.

        Raises:
            Error: If an exception occurs during the scrolling process.
        """

        try:
            browser_height = self.driver.execute_script(
                "return document.body.scrollHeight")
            for _ in range(times):
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);")
                sleep(self.scroll_pause_time)
                new_browser_height = self.driver.execute_script(
                    "return document.body.scrollHeight")
                if new_browser_height == browser_height:
                    break
                browser_height = new_browser_height
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def open_new_tab(self) -> None:
        """
        Opens a new tab in the browser.

        Raises:
            Error: If an exception occurs during the new tab opening process.
        """

        try:
            self.execute_script("window.open();")
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def open_new_tab_go(self, url: str) -> None:
        """
        Opens a new tab in the browser and navigates to the specified URL.

        Args:
            url (str): The URL to navigate to in the new tab.

        Raises:
            Error: If an exception occurs during the new tab opening or navigation process.
        """

        try:
            self.execute_script(
                f"var newWindow = window.open(); newWindow.location.href = '{
                    url}'"
            )
        except Exception as err:
            self.check_throw(Error(f"Unable to open new tab to {url}"))

    def get_current_iframe(self):
        """
        Returns the name of the current iframe.

        Returns:
            str: The name of the current iframe.

        Raises:
            Error: If an exception occurs during the retrieval of the current iframe name.
        """

        try:
            return self.execute_script("self.name")
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def switch_to_iframe(self, iframe: WebElement) -> None:
        """
        Switches the driver's focus to the specified iframe element.

        Args:
            iframe (WebElement): The iframe element to switch focus to.

        Raises:
            Error: If an exception occurs during the iframe switching process.
        """

        try:
            self.driver.switch_to.frame(iframe)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def switch_to_default_iframe(self) -> None:
        """
        Switches the driver's focus back to the default content.

        Raises:
            Error: If an exception occurs during the switching to default content process.
        """

        try:
            self.driver.switch_to.default_content()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    ## ELEMENT FUNCTIONS ##

    def press_modifer_key_send_keys(
            self, modifer_key: MODIFERKEYS, keys: Any = "") -> None:
        """
        Presses a modifier key while sending keys and then releases the modifier key.

        Args:
            modifer_key (MODIFERKEYS): The modifier key to press.
            keys (Any): The keys to send along with the modifier key (default is an empty string).

        Raises:
            Error: If an exception occurs during the key press and send keys process.
        """

        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key).send_keys(keys).key_up(modifer_key)
            action.perform()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def press_modifer_key(self, modifer_key: MODIFERKEYS) -> None:
        """
        Presses and releases a modifier key.

        Args:
            modifer_key (MODIFERKEYS): The modifier key to press and release.

        Raises:
            Error: If an exception occurs during the modifier key press and release process.
        """

        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key).key_up(modifer_key)
            action.perform()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def press_modifer_key_send_keys_on_element(
            self, element: WebElement, modifer_key: MODIFERKEYS, keys: Any = "") -> None:
        """
        Presses a modifier key while sending keys to a specific element and then releases the modifier key.

        Args:
            element (WebElement): The element to send keys to.
            modifer_key (MODIFERKEYS): The modifier key to press.
            keys (Any): The keys to send along with the modifier key (default is an empty string).

        Raises:
            Error: If an exception occurs during the key press, send keys, and release process.
        """

        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key, element).send_keys(
                keys, element).key_up(modifer_key, element)
            action.perform()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def press_modifer_key_on_element(
            self, element: WebElement, modifer_key: MODIFERKEYS) -> None:
        """
        Presses and releases a modifier key on a specific element.

        Args:
            element (WebElement): The element on which to press and release the modifier key.
            modifer_key (MODIFERKEYS): The modifier key to press and release.

        Raises:
            Error: If an exception occurs during the modifier key press and release process.
        """

        try:
            action = ActionChains(self.driver)
            action.key_down(modifer_key, element).key_up(modifer_key, element)
            action.perform()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_elements(self, xpath: str) -> WebElement:
        """
        Presses and releases a modifier key on a specific element.

        Args:
            element (WebElement): The element on which to press and release the modifier key.
            modifer_key (MODIFERKEYS): The modifier key to press and release.

        Raises:
            Error: If an exception occurs during the modifier key press and release process.
        """

        try:

            elements = WebDriverWait(
                self.driver, self.poll_time, poll_frequency=self.poll_frequency
            ).until(EC.presence_of_all_elements_located((By.XPATH, xpath)))

            for element in elements:
                WebDriverWait(
                    self.driver, self.poll_time, poll_frequency=self.poll_frequency
                ).until(EC.element_to_be_clickable(element))
            return elements
        except Exception as err:
            self.check_throw(Error(f"Failed to find elements: {xpath}"))

    def get_elements_until_none(self, xpath: str) -> WebElement:
        """
        Waits until elements matching the given XPath are present and returns them.

        Args:
            xpath (str): The XPath expression to locate the elements.

        Returns:
            Union[List[WebElement], bool]: The list of located WebElements if found, False otherwise.

        Raises:
            Error: If an exception occurs during the element location process.
        """

        try:
            elements = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                PresenceOfAllElementsLocatedIfNotEmpty((By.XPATH, xpath)))
            return elements if type(elements) == list else False
        except Exception as err:
            self.check_throw(Error(f"Failed to find elements: {xpath}"))

    def get_element_relative(
            self, parent_element: WebElement, xpath: str) -> WebElement:
        """
        Find a child element relative to the given parent element using an XPath.

        Args:
            parent_element (WebElement): The parent element from which to find the child.
            xpath (str): The XPath expression to locate the child element.

        Returns:
            WebElement: The found child element or None if not found.
        """
        try:
            return parent_element.find_element(By.XPATH, xpath)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find relative element: {xpath}"))
            return None

    def get_element(self, xpath: str) -> WebElement:
        """
        Waits until elements matching the given XPath are present.

        Args:
            xpath (str): The XPath expression to locate the elements.

        Returns:
            WebElement: The WebElement object representing the located elements.
        """

        try:
            return WebDriverWait(
                self.driver, self.poll_time, poll_frequency=self.poll_frequency
            ).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        except Exception as err:
            self.check_throw(Error(f"Failed to find element: {xpath}"))

    def try_to_get_element(self, xpath: str) -> WebElement:
        """
        Attempts to locate and return an element based on the provided XPath expression.

        Args:
            xpath (str): The XPath expression to locate the element.

        Returns:
            WebElement: The located WebElement object.

        Raises:
            Exception: If an exception occurs during the element location process.
        """

        try:
            return WebDriverWait(
                self.driver, self.poll_time, poll_frequency=self.poll_frequency
            ).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        except Exception as err:
            return False

    def get_element_by_tag_name(self, tag: str) -> WebElement:
        """
        Finds and returns the first element with the specified tag name.

        Args:
            tag (str): The tag name of the element to find.

        Returns:
            WebElement: The WebElement object representing the found element.
        """

        try:
            return self.driver.find_element(By.TAG_NAME, tag)
        except Exception as err:
            traceback.print_exc()

    def get_child_element(self, element: WebElement, xpath: str) -> WebElement:
        """
        Finds a child element within a parent element by XPath and waits for it to be clickable.

        Args:
            element (WebElement): The parent element to search within.
            xpath (str): The XPath expression to locate the child element.

        Returns:
            WebElement: The located child WebElement object.

        Raises:
            Error: If an exception occurs during the child element location process.
        """

        try:
            c_element = element.find_element(By.XPATH, xpath)
            return WebDriverWait(
                self.driver, self.poll_time, poll_frequency=self.poll_frequency
            ).until(EC.element_to_be_clickable(c_element))
        except Exception as err:
            self.check_throw(Error(f"Failed to find element: {xpath}"))

    def find_and_send_modifer_key(self, xpath: str, key: Any) -> None:
        """
        Finds an element by XPath, waits for it to be clickable, and sends keys to it.

        Args:
            xpath (str): The XPath expression to locate the element.
            key (Any): The keys to send to the element.

        Raises:
            Error: If an exception occurs during the element location or key sending process.
        """

        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            element.send_keys(key)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and send keys: {key}")
            )

    def find_and_send_modifer_key(
            self, element: WebElement, modifier_key: Any) -> None:
        """
        Finds an element and sends a modifier key to it.

        Args:
            element (WebElement): The element to send the modifier key to.
            modifier_key (Any): The modifier key to send to the element.

        Raises:
            Error: If an exception occurs during the element location or key sending process.
        """

        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located(element))
            element.send_keys(modifier_key)
        except Exception as err:
            self.check_throw(
                Error(
                    f"Failed to find element: {element} and send keys: {modifier_key}")
            )

    def send_modifer_key(self, modifier_key) -> None:
        try:
            action = ActionChains(self.driver)
            action.key_down(modifier_key).key_up(modifier_key)
            action.perform()
        except Exception as err:
            traceback.print_exc()

    def send_modifer_key_to_window(self, window, modifier_key) -> None:
        try:
            action = ActionChains(self.driver)
            action.key_down(modifier_key, window).key_up(modifier_key, window)
            action.perform()
        except Exception as err:
            traceback.print_exc()

    def find_and_click_send_modifer_key(
            self, xpath: str, modifer_key: Any, keys: Any) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            self.click_element(element)
            self.press_modifer_key_send_keys(modifer_key, keys)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and send keys: {keys}")
            )

    def find_and_send_keys(self, xpath: str, keys: Any) -> None:
        """
        Find an element by XPath, send keys to the element, and verify the keys sent.

        Args:
            xpath : str
                The XPath locator of the element to find.
            keys : Any
                The keys to send to the element.

        Raises:
            Error
                If the element cannot be found or keys cannot be sent.

        Returns:
            None
        """

        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForKeysVerification((By.XPATH, xpath), keys))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and send keys: {keys}")
            )

    def find_and_send_keys_with_delay(
            self, xpath: str, keys: Any, delay=1) -> None:
        """
        Find an element by XPath, send keys with a delay, and verify the keys sent.

        Args:
            xpath : str
                The XPath locator of the element to find.
            keys : Any
                The keys to send to the element.
            delay : int, optional
                The delay in seconds before sending the keys, by default 1.

        Raises:
            Error
                If the element cannot be found or keys cannot be sent.

        Returns:
            None
        """
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForKeysVerificationWithDelay((By.XPATH, xpath), keys, delay=1))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and send keys: {keys}")
            )

    def find_click_and_send_keys(self, xpath: str, keys: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            self.click_element(element)
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForKeysVerification((By.XPATH, xpath), keys))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and send keys: {keys}")
            )

    def find_and_click(self, xpath: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            self.click_element(element)

        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def find_and_click_and_wait_for_element(
            self, xpath: str, element_xpath: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            self.click_element(element)
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, element_xpath)))

        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def find_click_and_send_keys_and_go(
            self, xpath: str, keys: str, url: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            self.click_element(element)
            self.driver.go(url)

        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_element(self, element: WebElement) -> None:
        try:
            action = ActionChains(self.driver)
            action.scroll_to_element(element)
            action.move_to_element(element)
            action.click(element)
            action.perform()

        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {element} and click."))

    def try_to_click_element(self, element: WebElement) -> None:
        try:
            if element:
                action = ActionChains(self.driver)
                action.scroll_to_element(element)
                action.move_to_element(element)
                action.click(element)
                action.perform()

        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {element} and click."))

    def click_chain_elements_infinitely(
            self, xpaths: list, pause_time: int = 0) -> None:
        while True:
            try:
                for xpath in xpaths:
                    WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                        EC.presence_of_element_located((By.XPATH, xpath)))
                    element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                        EC.element_to_be_clickable((By.XPATH, xpath)))
                    self.click_element(element)
                sleep(pause_time)
            except Exception as err:
                self.check_throw(
                    Error(f"Failed to find element: {xpath} and click."))

    def click_chain_elements(
            self, xpaths: list, pause_time: int = 0, loop_count: int = 10) -> None:
        try:
            for _ in range(loop_count):
                for xpath in xpaths:
                    WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                        EC.presence_of_element_located((By.XPATH, xpath)))
                    element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                        EC.element_to_be_clickable((By.XPATH, xpath)))
                    self.click_element(element)
                sleep(pause_time)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_all_elements_and_scroll(
            self, xpath: str, scroll_count=1) -> None:
        try:
            elements = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath)))
            for element in elements:
                WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                    EC.element_to_be_clickable(element))
                self.click_element(element)

            self.scroll_to_bottom(scroll_count)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_and_wait_for_load(self, xpath: str):
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForLoadAfterClick((By.XPATH, xpath)))
        except Exception as err:
            print(err)
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_and_wait_for_element(self, xpath: str, xpath2: str):
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForElementAfterClick((By.XPATH, xpath), (By.XPATH, xpath2)))
        except Exception as err:
            print(err)
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_and_wait_for_html_load(self, xpath: str):
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForLoadAfterClick((By.XPATH, xpath)))
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForHtmlLoadAfterClick((By.XPATH, xpath)))
        except Exception as err:
            print(err)
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_element_and_wait_for_load(self, element: WebElement):
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable(element))
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForHtmlLoadAfterClickElement(element))
        except Exception as err:
            print(err)
            self.check_throw(
                Error("Failed to find element and click."))

    def wait_for_element(self, xpath: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def wait_to_click_element(self, xpath: str, wait: int = 1) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitElementToBeClickable((By.XPATH, xpath), wait))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def wait_for_element_to_disappear_by_xpath(
            self, xpath: str, wait: int = 1) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForElementToBeStale((By.XPATH, xpath), wait))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def wait_for_element_to_disappear(
            self, element: str, wait: int = 1) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WaitForElementToBeStale(element, wait))
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {element} and click."))

    def element_exists(self, xpath: str) -> bool:
        try:
            return bool(
                element := WebDriverWait(
                    self.driver, self.poll_time, poll_frequency=self.poll_frequency
                ).until(EC.presence_of_element_located((By.XPATH, xpath)))
            )
        except Exception as err:
            return False

    def click_all_elements(self, xpath: str) -> None:
        try:
            processed_elements = set()
            elements = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath)))
            for element in elements:
                if element in processed_elements:
                    continue
                WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                    EC.element_to_be_clickable(element))
                action = ActionChains(self.driver)
                action.move_to_element(element)
                action.click(element)
                action.perform()
                processed_elements.add(element)
            # elements = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
            #     EC.presence_of_all_elements_located((By.XPATH, xpath)))
            # for element in elements:
            #     WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
            #         EC.element_to_be_clickable(element))
            #     self.click_element(element)
        except Exception as err:
            self.check_throw(
                Error(f"Failed to find element: {xpath} and click."))

    def click_all_elements_and_reload(self, xpath: str) -> None:
        try:
            elements = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath)))
            for element in elements:
                WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                    EC.element_to_be_clickable(element))
                self.click_element(element)

            self.driver.refresh()
        except Exception as err:
            self.check_throw(
                Error("Failed to find element: {} and click.".format(xpath)))

    ## FRAME FUNCTIONS ##

    def find_frame_switch(self, xpath: str) -> None:
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.frame_to_be_available_and_switch_to_it((By.XPATH, xpath)))
        except Exception as err:
            self.check_throw(
                Error("Failed to find element: {} and switch.".format(xpath)))

    def get_window_handles(self):
        try:
            return self.driver.window_handles
        except Exception as err:
            self.check_throw(
                Error("Failed to get current window handles. ERROR: {}".format(err)))

    def get_current_window_handle(self):
        try:
            return self.driver.current_window_handle
        except Exception as err:
            self.check_throw(
                Error("Failed to save current window handle. ERROR: {}".format(err)))

    def find_window_handle_switch_to_it_close_previous(self, index):
        try:
            WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WindowHandleToBeAvailableSwitchClosePrevious(index))
        except Exception as err:
            self.check_throw(
                Error("Failed to find window index: {} and switch.".format(index)))

    def find_window_handle_switch_to_it(self, index):
        try:
            window = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WindowHandleToBeAvailable(index))
            self.driver.switch_to.window(window)
        except Exception as err:
            self.check_throw(
                Error("Failed to find window index: {} and switch.".format(index)))

    def get_window_handle_id(self, index: int) -> str:
        try:
            return self.driver.window_handles[index]
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def switch_to_latest_window(self) -> None:
        try:
            window = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                WindowHandleToBeAvailable(len(self.driver.window_handles) - 1))
            self.driver.switch_to.window(window)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def switch_to_first_window(self) -> None:
        try:
            first_window_index = self.driver.window_handles[0]
            self.driver.switch_to.window(first_window_index)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def close_current_window(self) -> None:
        try:
            self.driver.close()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def switch_to_parent_frame(self) -> None:
        try:
            self.driver.switch_to.parent_frame()
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def check_element_for_value_change(self, xpath: str, forever=False):
        if forever:
            value_changed = not False
            while value_changed:
                try:
                    WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                        WaitForValueToChange((By.XPATH, xpath)))
                    value_changed = not True
                except Exception as err:
                    self.check_throw(Error(f"ERROR: {err}"))
        else:
            try:
                WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                    WaitForValueToChange((By.XPATH, xpath)))
            except Exception as err:
                self.check_throw(Error(f"ERROR: {err}"))

    def check_node_css_property(
            self, xpath: str, property: str, search: str, value: str, return_value=False) -> Any:
        try:
            search_str = re.compile(search)
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            element_property = element.value_of_css_property(property)
            if not (match := search_str.findall(element_property)):
                return False

            match_str = match.group(1)
            if match_str == value:
                return match_str if return_value else True
            return element_property if return_value else False
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def execute_script(self, script: str, return_value=False,
                       node: WebElement = None) -> Any:
        try:
            if return_value:
                return self.driver.execute_script(script)
            else:
                self.driver.execute_script(script)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def execute_async_script(self, script: str, return_value=False) -> Any:
        try:
            if return_value:
                return self.driver.execute_async_script(script)
            else:
                self.driver.execute_async_script(script)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_text_from_node_convert(self, xpath: str, ctype: Any) -> Any:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            return ctype(element.text)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_text_from_node(self, xpath: str) -> str:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            return element.text
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_text_from_node_element(self, element: WebElement) -> str:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable(element))
            return element.text
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def set_attribute_of_node(
            self, xpath: str, attribute: str, value: str) -> None:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            self.execute_script(
                f"document.evaluate('{xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.setAttribute('{
                    attribute}', '{value}')"
            )
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def remove_attribute_of_node(self, xpath: str, attribute: str) -> None:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            self.execute_script(
                f"document.evaluate('{
                    xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.removeAttribute('{attribute}');"
            )
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_property_from_node(self, xpath: str, attr: str) -> Any:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            return element.get_property(attr)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_attribute_from_node(self, xpath: str, attr: str) -> Any:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            return element.get_attribute(attr)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_inner_html_from_node(self, xpath: str) -> str:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            return element.get_attribute('innerHTML')
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def get_outer_html_from_node(self, xpath: str) -> str:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            return element.get_attribute('outerHTML')
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def check_node_for_property(self, xpath: str, property: str) -> bool:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            return bool(element.get_property(property))
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))

    def select_option_from_dropdown(
            self, xpath: str, select_type: DROPDOWNTYPE, value: Any) -> None:
        try:
            element = WebDriverWait(self.driver, self.poll_time, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            select = Select(element)
            if select_type == DROPDOWNTYPE.INDEX:
                select.select_by_index(value)
            elif select_type == DROPDOWNTYPE.VALUE:
                select.select_by_value(value)
            elif select_type == DROPDOWNTYPE.TEXT:
                select.select_by_visible_text(value)
        except Exception as err:
            self.check_throw(Error(f"ERROR: {err}"))
