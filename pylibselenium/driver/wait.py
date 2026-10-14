import logging
import random
from time import sleep
from urllib.parse import urldefrag

from selenium.common.exceptions import (
    InvalidSelectorException,
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchFrameException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
    UnexpectedAlertPresentException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Set up logging
logger = logging.getLogger(__name__)

# Errors that polling can never recover from. The conditions below re-raise them so
# WebDriverWait aborts immediately and the real cause reaches the caller, instead of being
# hidden behind a generic timeout.
_FATAL = (
    NoSuchWindowException,
    NoSuchFrameException,
    InvalidSessionIdException,
    UnexpectedAlertPresentException,
    InvalidSelectorException,
    TimeoutException,
)

# WebDriver key codes (``Keys.ENTER`` and friends) live in the Unicode private use area. They
# never show up in an input's value, so typed-text verification has to skip them.
_KEY_CODE_MIN, _KEY_CODE_MAX = "", ""


def _contains_key_codes(text) -> bool:
    """True when ``text`` holds at least one WebDriver key code."""
    return any(_KEY_CODE_MIN <= ch <= _KEY_CODE_MAX for ch in str(text))


def _is_stale(element) -> bool:
    """True once a WebElement reference no longer points at a live node (same probe as EC.staleness_of)."""
    if element is None:
        return False
    try:
        element.is_enabled()
        return False
    except (StaleElementReferenceException, NoSuchElementException):
        return True


def _ready(driver) -> bool:
    """True when the document in the current browsing context has finished loading."""
    return driver.execute_script("return document.readyState") == "complete"


def _url_key(url):
    """Strip the fragment so a '#anchor' click does not count as a page change."""
    return urldefrag(url).url if url else url


def _capture_root(driver):
    """The current document's <html> element, or None where there is no document (native apps)."""
    try:
        return driver.find_element(By.TAG_NAME, "html")
    except WebDriverException:
        return None


def _capture_url(driver):
    """The current fragment-stripped URL, or None if it cannot be read right now."""
    try:
        return _url_key(driver.current_url)
    except WebDriverException:
        return None


def _locator_present(driver, locator) -> bool:
    """True when at least one element matches the locator."""
    return bool(driver.find_elements(*locator))


class PresenceOfAllElementsLocatedIfNotEmpty:
    """Check if elements located by the locator are present and not empty."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            elements = driver.find_elements(*self.locator)
            return elements if elements else False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class AllElementsVisibleAndEnabled:
    """
    Every element matching the locator is displayed and enabled; returns the list.

    One ``find_elements`` call, one ``is_displayed`` per element (WebDriver's own visibility
    atom, so hidden overflow and zero-size elements are judged the same way as
    ``EC.visibility_of_all_elements_located``) and a single batched script for the enabled
    check, instead of one full ``WebDriverWait`` per element.
    """

    _JS = "return arguments[0].every(function (e) { return !e.matches(':disabled'); });"

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            elements = driver.find_elements(*self.locator)
            if not elements or not all(element.is_displayed() for element in elements):
                return False
            return elements if driver.execute_script(self._JS, elements) else False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForElementToBeStale:
    """
    Wait for an element located by the locator to become stale.

    Deprecated: prefer ``ElementIsAbsent`` / ``ElementIsStale``; this condition sleeps inside
    the poll loop.
    """

    def __init__(self, locator, wait):
        self.locator = locator
        self.wait = wait

    def __call__(self, driver):
        try:
            driver.find_element(*self.locator)
            sleep(self.wait)
            return False
        except (NoSuchElementException, StaleElementReferenceException):
            return True
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WindowHandleToBeAvailable:
    """Check if a window handle at a specific index is available."""

    def __init__(self, index):
        self.index = index

    def __call__(self, driver):
        try:
            return driver.window_handles[self.index]
        except IndexError:
            return False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class NewWindowOpened:
    """Return the newest window handle that was not in ``previous_handles``."""

    def __init__(self, previous_handles):
        self.previous_handles = set(previous_handles or ())

    def __call__(self, driver):
        try:
            new_handles = [h for h in driver.window_handles if h not in self.previous_handles]
            return new_handles[-1] if new_handles else False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForPageLoad:
    """Check if the page has fully loaded by checking document.readyState."""

    def __call__(self, driver):
        try:
            return _ready(driver)
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForElementReadyState:
    """Check if an element located by the locator is in a ready state."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            return element if _ready(driver) else False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WindowHandleToBeAvailableSwitchClosePrevious:
    """Switch to the window handle at ``index`` and close the window that was focused before."""

    def __init__(self, index):
        self.index = index

    def __call__(self, driver):
        try:
            window_handles = driver.window_handles
            if len(window_handles) <= self.index:
                return False
            target = window_handles[self.index]
            current = driver.current_window_handle
            if current != target:
                driver.close()
                driver.switch_to.window(target)
            return True
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitElementToBeClickable:
    """Wait for an element located by the locator to be clickable and click it."""

    def __init__(self, locator, wait):
        self.locator = locator
        self.wait = wait

    def __call__(self, driver):
        try:
            element = WebDriverWait(driver, self.wait).until(
                EC.element_to_be_clickable(self.locator))
            element.click()
            return True
        except TimeoutException:
            return False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForValueToChange:
    """Wait for the text of an element located by the locator to change from its first reading."""

    def __init__(self, locator):
        self.locator = locator
        self.previous_text = None

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            current_text = element.text
            if self.previous_text is None:
                self.previous_text = current_text
                return False
            return self.previous_text != current_text
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForElementToBeRemoved:
    """Deprecated: use ``ElementIsStale``. Waits up to 10 s inside the poll for the element to go stale."""

    def __init__(self, element):
        self.element = element

    def __call__(self, driver):
        try:
            WebDriverWait(driver, 10).until(EC.staleness_of(self.element))
            return True
        except TimeoutException:
            return False
        except _FATAL:
            raise
        except WebDriverException:
            return False


class ElementIsAbsent:
    """True while no element matches the locator (nothing in the DOM at all)."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            return len(driver.find_elements(*self.locator)) == 0
        except _FATAL:
            raise
        except WebDriverException:
            return False


class ElementIsStale:
    """True once a previously found WebElement is detached from the DOM or its document is gone."""

    def __init__(self, element):
        self.element = element

    def __call__(self, driver):
        try:
            return _is_stale(self.element)
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForPageChange:
    """Wait until the browser has left the page that ``old_root`` / ``old_url`` were captured on.

    The page counts as changed once the captured <html> element is stale (the document was
    replaced, including inside the current iframe) or the fragment-stripped URL differs (SPA
    pushState navigation). The condition then waits for ``document.readyState == "complete"``
    and, when ``settle`` is set, for one extra poll on which the *new* document is still live and
    complete, so redirect chains and the transient about:blank Chrome can expose do not return
    early.

    ``element`` is only consulted when ``old_root`` is None (contexts without a document, such as
    Appium native apps). On a web page a button that is re-rendered on click must not count as a
    page change.
    """

    def __init__(self, old_root, old_url=None, element=None, settle=True):
        self.old_root = old_root
        self.old_url = _url_key(old_url)
        self.element = element
        self.settle = settle
        self.changed = False
        self._new_root = None

    def _has_changed(self, driver) -> bool:
        if self.changed:
            return True
        if self.old_root is not None:
            self.changed = _is_stale(self.old_root)
        elif self.element is not None:
            self.changed = _is_stale(self.element)
        if not self.changed and self.old_url is not None:
            self.changed = _capture_url(driver) != self.old_url
        return self.changed

    def __call__(self, driver):
        try:
            if not self._has_changed(driver):
                return False
            if self.old_root is None:
                # No document to check readiness on (native context).
                return True
            if not _ready(driver):
                self._new_root = None
                return False
            if not self.settle:
                return True
            if self._new_root is not None and not _is_stale(self._new_root):
                return True
            # First poll on the new document: remember it and confirm it is still there next time.
            self._new_root = _capture_root(driver)
            return False
        except _FATAL:
            raise
        except WebDriverException:
            self._new_root = None
            return False


class WaitForPageChangeAfterClick:
    """Click an element once it can be clicked, then wait for the page to change.

    Phase 1 retries ``find_element`` + ``element.click()`` on every poll until the click lands (a
    raw WebDriver click raises when an overlay intercepts it, so retrying is meaningful). The
    <html> root and the URL are captured right before the click. Phase 2 delegates to
    :class:`WaitForPageChange`. With ``require_navigation=False`` the element-level signals the
    legacy ``click_and_wait_for_*`` methods rely on also count: the clicked element went stale,
    the locator no longer matches anything, or (``accept_disabled``) the element became disabled.
    """

    def __init__(self, locator=None, element=None, require_navigation=True, accept_disabled=False, settle=True):
        if locator is None and element is None:
            raise ValueError("Either locator or element is required")
        self.locator = locator
        self.element = element
        self.require_navigation = require_navigation
        self.accept_disabled = accept_disabled
        self.settle = settle
        self.clicked = False
        self._page = None

    def _click(self, driver) -> None:
        element = self.element if self.element is not None else driver.find_element(*self.locator)
        old_root = _capture_root(driver)
        old_url = _capture_url(driver)
        element.click()
        self.element = element
        self.clicked = True
        self._page = WaitForPageChange(
            old_root,
            old_url=old_url,
            element=element if old_root is None else None,
            settle=self.settle,
        )

    def _element_changed(self, driver) -> bool:
        if _is_stale(self.element):
            return True
        if self.locator is not None and not _locator_present(driver, self.locator):
            return True
        if self.accept_disabled and not self.element.is_enabled():
            return True
        return False

    def __call__(self, driver):
        try:
            if not self.clicked:
                self._click(driver)
                return False
            if self._page(driver):
                return True
            if self.require_navigation:
                return False
            return self._element_changed(driver) and _ready(driver)
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForHtmlLoadAfterClick(WaitForPageChangeAfterClick):
    """Wait for the HTML to load after an element located by the locator is clicked."""

    def __init__(self, locator):
        super().__init__(locator=locator, require_navigation=False, accept_disabled=False, settle=False)


class WaitForHtmlLoadAfterClickElement(WaitForPageChangeAfterClick):
    """Wait for the HTML to load after a specific element is clicked."""

    def __init__(self, element):
        super().__init__(element=element, require_navigation=False, accept_disabled=True, settle=False)


class WaitForLoadAfterClick(WaitForPageChangeAfterClick):
    """Wait for an element to load after being clicked."""

    def __init__(self, locator):
        super().__init__(locator=locator, require_navigation=False, accept_disabled=True, settle=False)


class WaitForLoadAfter:
    """Deprecated: True once the located element is disabled."""

    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            return not element.is_enabled()
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForElementAfterClick:
    """Wait for an element to appear after clicking another element."""

    def __init__(self, locator, waited_locator):
        self.locator = locator
        self.waited_locator = waited_locator
        self.clicked = False

    def __call__(self, driver):
        try:
            if not self.clicked:
                driver.find_element(*self.locator).click()
                self.clicked = True
            # Only look for the awaited element from here on; the clicked one may be gone.
            return _locator_present(driver, self.waited_locator)
        except _FATAL:
            raise
        except WebDriverException:
            return False


class _MaxLengthMixin:
    """Shared ``maxlength`` handling for the typed-text verification conditions."""

    max_length = None
    max_length_set = False
    max_length_fallback = None

    def _get_max_length(self, element):
        """Get the maxlength attribute with proper validation and fallback logic."""
        maxlength_attr = None
        try:
            maxlength_attr = element.get_attribute("maxlength")
            if maxlength_attr is not None and maxlength_attr.strip():
                max_length = int(maxlength_attr)
                if max_length > 0:
                    return max_length
                logger.warning(f"Invalid maxlength value: {maxlength_attr}. Using fallback.")
            else:
                logger.debug("No maxlength attribute found on element.")
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse maxlength attribute '{maxlength_attr}': {e}. Using fallback.")
        except Exception as e:
            logger.warning(f"Error getting maxlength attribute: {e}. Using fallback.")

        # Fallback logic: use provided fallback, element's current value length, or reasonable default
        if self.max_length_fallback is not None:
            return self.max_length_fallback

        try:
            current_value = element.get_property("value") or ""
            current_length = len(str(current_value))
            # Use current length + some buffer, but cap at reasonable maximum
            return min(current_length + 100, 10000)
        except Exception:
            # Final fallback to a reasonable default
            return 1000

    def set_max_length(self, element):
        self.max_length = self._get_max_length(element)
        self.max_length_set = True


class WaitForKeysVerification(_MaxLengthMixin):
    """
    Type ``keys`` into the element and succeed once its value reads back correctly.

    ``element`` (optional) is used directly until it goes stale, which saves a ``find_element``
    per poll; ``click=False`` skips the focusing click when the caller already clicked. On
    re-polls the value is read first and only retyped on a mismatch. When ``keys`` contain a
    WebDriver key code (``Keys.ENTER`` ...) the value can never match, so the condition succeeds
    right after typing instead of re-sending the key on every poll.
    """

    def __init__(self, locator, keys, max_length_fallback=None, click=True, element=None):
        self.locator = locator
        self.keys = str(keys)
        self.max_length_set = False
        self.max_length_fallback = max_length_fallback
        self.click = click
        self.element = element
        self.typed = False

    def _resolve_element(self, driver):
        if self.element is not None and not _is_stale(self.element):
            return self.element
        if self.locator is None:
            raise StaleElementReferenceException("The element went stale and no locator was given to re-find it")
        self.element = driver.find_element(*self.locator)
        return self.element

    def _type(self, driver, element):
        element.clear()
        element.send_keys(self.keys)

    def __call__(self, driver):
        try:
            element = self._resolve_element(driver)
            if not self.max_length_set:
                self.set_max_length(element)
            expected = self.keys[:int(self.max_length)]
            verify = not _contains_key_codes(self.keys)
            if self.typed and verify and str(element.get_property("value")) == expected:
                return True
            if self.click:
                element.click()
            self._type(driver, element)
            self.typed = True
            if not verify:
                return True
            return str(element.get_property("value")) == expected
        except _FATAL:
            raise
        except WebDriverException:
            return False


class WaitForKeysVerificationWithDelay(WaitForKeysVerification):
    """
    Like ``WaitForKeysVerification`` but presses the keys one at a time with a random pause of up
    to ``delay`` seconds between them (human-like typing).
    """

    def __init__(self, locator, keys, delay, max_length_fallback=None, click=True, element=None):
        super().__init__(locator, keys, max_length_fallback=max_length_fallback, click=click, element=element)
        self.delay = max(float(delay or 0), 0.0)

    def _type(self, driver, element):
        element.clear()
        # Build the action chain once and perform once.
        action = ActionChains(driver)
        for key in self.keys:
            action.key_down(key)
            action.pause(random.uniform(0, self.delay))
            action.key_up(key)
        action.perform()
