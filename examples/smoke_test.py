#!/usr/bin/env python3
"""
Headless browser smoke test for pylibselenium.

Serves ``examples/fixtures`` on a local port and drives it with the public ``DriverClient`` API,
once per requested browser. Every case prints PASS/FAIL; the process exits non-zero when any
case failed.

    python examples/smoke_test.py                       # chrome and firefox
    python examples/smoke_test.py --browser chrome      # one browser
    python examples/smoke_test.py --source              # import the checkout instead of the installed package
    python examples/smoke_test.py --skip-legacy         # do not start a second browser for the legacy constructors

Without ``executable_path`` the drivers are resolved by Selenium Manager, so a matching
chromedriver/geckodriver is downloaded on first use. Strip stale driver directories from PATH if
Selenium picks up an old one.
"""
import argparse
import functools
import http.server
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", action="append", choices=["chrome", "firefox", "edge"],
                        help="browser to test; repeatable (default: chrome and firefox)")
    parser.add_argument("--source", action="store_true", help="import pylibselenium from this checkout")
    parser.add_argument("--skip-legacy", action="store_true", help="skip the legacy-constructor case (second browser start)")
    parser.add_argument("--skip-download", action="store_true", help="skip the download case")
    parser.add_argument("--keep", action="store_true", help="leave the browsers open afterwards")
    parser.add_argument("--poll-time", type=float, default=10.0)
    return parser.parse_args()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_fixtures():
    handler = functools.partial(QuietHandler, directory=str(FIXTURES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class CommandCounter:
    """Count WebDriver commands (one HTTP round trip each) issued inside the block."""

    def __init__(self):
        self.count = 0

    def __enter__(self):
        from selenium.webdriver.remote.remote_connection import RemoteConnection
        self._cls = RemoteConnection
        self._original = RemoteConnection.execute
        counter = self

        def execute(connection, command, params):
            counter.count += 1
            return counter._original(connection, command, params)

        RemoteConnection.execute = execute
        return self

    def __exit__(self, *exc):
        self._cls.execute = self._original
        return False


class Suite:
    def __init__(self, browser):
        self.browser = browser
        self.results = []

    def check(self, label, condition, detail=""):
        ok = bool(condition)
        self.results.append((label, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not ok else ""))
        return ok

    def run(self, label, fn):
        try:
            fn()
        except Exception as err:  # keep going; the failure is recorded
            self.check(label, False, f"{type(err).__name__}: {err}")

    @property
    def failed(self):
        return [r for r in self.results if not r[1]]


def build_client(browser, download_dir, args):
    from pylibselenium import DriverClient
    common = dict(poll_time=args.poll_time, poll_frequency=0.25, throw=True, keep_open=args.keep)
    if browser == "chrome":
        return DriverClient.chrome(headless=True, download_dir=download_dir,
                                   arguments=["--no-sandbox", "--disable-gpu", "--window-size=1200,900"], **common)
    if browser == "edge":
        return DriverClient.edge(headless=True, download_dir=download_dir,
                                 arguments=["--no-sandbox", "--disable-gpu", "--window-size=1200,900"], **common)
    return DriverClient.firefox(headless=True, download_dir=download_dir,
                                arguments=["--width=1200", "--height=900"], **common)


def run_browser(browser, base_url, args):
    from selenium.common.exceptions import TimeoutException
    from pylibselenium import DROPDOWNTYPE, MODIFERKEYS, Error, PerformanceClient, ProfileClient

    suite = Suite(browser)
    print(f"\n=== {browser} ===")
    download_dir = Path(tempfile.mkdtemp(prefix=f"pylibselenium-smoke-{browser}-"))
    url = lambda name: f"{base_url}/{name}"
    try:
        client = build_client(browser, str(download_dir), args)
    except Exception as err:
        suite.check("start browser", False, f"{type(err).__name__}: {err}")
        return suite
    suite.check("start browser", True)

    with client:
        def navigation():
            client.go_and_wait_for_load(url("index.html"))
            suite.check("go_and_wait_for_load + get_title", "fixture" in client.get_title())
            suite.check("element_exists", client.element_exists('//h1[@id="title"]'))
            suite.check("element_does_not_exist", client.element_does_not_exist('//h1[@id="nope"]', timeout=1))
            suite.check("get_text_from_node", client.get_text_from_node('//h1[@id="title"]') == "pylibselenium fixture")
            suite.check("get_page_source", "pylibselenium fixture" in client.get_page_source())
            suite.check("get_attribute_from_node", client.get_attribute_from_node('//span[@id="later"]', "data-state") in ("pending", "ready"))
        suite.run("navigation", navigation)

        def round_trips():
            with CommandCounter() as counter:
                client.find_and_click('//button[@id="counter"]')
            suite.check(f"find_and_click round trips = {counter.count}", counter.count <= 5, str(counter.count))
            suite.check("find_and_click clicked", client.get_text_from_node('//span[@id="counter-value"]') == "1")
            with CommandCounter() as counter:
                elements = client.get_elements('//ul[@id="ten"]/li')
            suite.check(f"get_elements(10) -> 10 elements, round trips = {counter.count}", len(elements) == 10 and counter.count <= 13, str(counter.count))
            with CommandCounter() as counter:
                client.find_and_send_keys('//input[@id="text"]', "hello world")
            value = client.get_property_from_node('//input[@id="text"]', "value")
            suite.check(f"find_and_send_keys verified, round trips = {counter.count}", value == "hello world" and counter.count <= 12, f"{value!r} / {counter.count}")
        suite.run("round trips", round_trips)

        def typing():
            client.find_and_send_keys('//input[@id="short"]', "1234567890")
            suite.check("find_and_send_keys respects maxlength", client.get_property_from_node('//input[@id="short"]', "value") == "12345")
            started = time.monotonic()
            client.find_and_send_keys('//input[@id="enter-input"]', "abc" + MODIFERKEYS.ENTER)
            elapsed = time.monotonic() - started
            suite.check("find_and_send_keys with ENTER key code returns promptly", elapsed < args.poll_time / 2, f"{elapsed:.1f}s")
            suite.check("ENTER key code was delivered", client.get_text_from_node('//span[@id="enter-pressed"]') == "yes")
            client.find_click_and_send_keys('//input[@id="text2"]', "clicked then typed")
            suite.check("find_click_and_send_keys", client.get_property_from_node('//input[@id="text2"]', "value") == "clicked then typed")
            client.find_and_send_keys_with_delay('//input[@id="text"]', "slow", delay=0.02)
            suite.check("find_and_send_keys_with_delay", client.get_property_from_node('//input[@id="text"]', "value") == "slow")
            client.set_attribute_of_node('//input[@id="text"]', "data-x", "1")
            suite.check("set_attribute_of_node", client.get_attribute_from_node('//input[@id="text"]', "data-x") == "1")
            client.remove_attribute_of_node('//input[@id="text"]', "data-x")
            suite.check("remove_attribute_of_node", client.get_attribute_from_node('//input[@id="text"]', "data-x") is None)
        suite.run("typing", typing)

        def elements():
            started = time.monotonic()
            try:
                client.get_elements('//ul[@id="mixed"]/li/button', timeout=1)
                suite.check("get_elements fails when one element is disabled", False)
            except Error:
                suite.check("get_elements fails when one element is disabled", 0.9 < time.monotonic() - started < 3)
            suite.check("get_elements_until_none", len(client.get_elements_until_none('//ul[@id="items"]/li/button')) == 5)
            suite.check("try_to_get_element missing -> False", client.try_to_get_element('//nope', timeout=0) is False)
            suite.check("try_click missing -> False", client.try_click('//button[@id="nope"]', timeout=0) is False)
            suite.check("try_click present -> True", client.try_click('//button[@id="btn-remove2"]') is True)
            suite.check("try_click removed the button", client.element_does_not_exist('//button[@id="btn-remove2"]', timeout=2))
            count = client.click_elements_until_none('//ul[@id="items"]/li/button')
            suite.check("click_elements_until_none processed 5", count == 5, str(count))
            suite.check("items are gone", client.element_does_not_exist('//ul[@id="items"]/li', timeout=1))
            suite.check("js_click reaches a covered button", (client.js_click('//button[@id="covered"]'), client.get_text_from_node('//span[@id="covered-result"]') == "clicked")[1])
            suite.check("click_and_wait_for_html_load", client.click_and_wait_for_html_load('//button[@id="btn-remove"]'))
        suite.run("elements", elements)

        def dropdown():
            client.select_option_from_dropdown('//select[@id="sel"]', DROPDOWNTYPE.VALUE, "b")
            suite.check("select_option_from_dropdown + get_selected_option", client.get_selected_option('//select[@id="sel"]') == "Bee")
            suite.check("get_dropdown_options", client.get_dropdown_options('//select[@id="sel"]') == ["Ay", "Bee", "Cee"])
        suite.run("dropdown", dropdown)

        def frames():
            with client.frame('//iframe[@id="outer"]'):
                suite.check("frame(): inside outer", client.element_exists('//p[@id="f1"]', timeout=3))
                suite.check("get_current_iframe", client.get_current_iframe() == "outer")
                with client.frame('//iframe[@id="inner"]'):
                    suite.check("frame(): nested inner", client.element_exists('//p[@id="f2"]', timeout=3))
                suite.check("frame(): back in outer after nested block", client.element_exists('//p[@id="f1"]', timeout=1))
            suite.check("frame(): back in top document", client.element_exists('//h1[@id="title"]', timeout=1))
            client.find_frame_switch('//iframe[@id="outer"]')
            suite.check("find_frame_switch", client.element_exists('//p[@id="f1"]', timeout=1))
            client.switch_to_default_iframe()
            suite.check("switch_to_default_iframe", client.element_exists('//h1[@id="title"]', timeout=1))
        suite.run("frames", frames)

        def windows():
            handles = client.get_window_handles()
            client.find_and_click('//a[@id="newtab"]')
            new_handle = client.wait_for_new_window(handles)
            suite.check("wait_for_new_window", bool(new_handle))
            client.switch_to_latest_window(previous_handles=handles)
            suite.check("switch_to_latest_window(previous_handles)", client.wait_for_title_contains("Page Two", timeout=5))
            client.close_current_window()
            client.switch_to_first_window()
            suite.check("close_current_window + switch_to_first_window", "fixture" in client.get_title())
            with client.new_tab(url("page2.html")) as handle:
                suite.check("new_tab(): on the new tab", client.get_title() == "Page Two" and handle == client.get_current_window_handle())
            suite.check("new_tab(): closed and back", "fixture" in client.get_title() and len(client.get_window_handles()) == 1)
            client.open_new_tab_go(url("page2.html"))
            suite.check("open_new_tab_go keeps focus", "fixture" in client.get_title() and len(client.get_window_handles()) == 2)
            suite.check("switch_to_window_by_title", client.switch_to_window_by_title("Page Two") and client.get_title() == "Page Two")
            with client.window(0):
                suite.check("window(0)", "fixture" in client.get_title())
            suite.check("window(): restored", client.get_title() == "Page Two")
            client.switch_to_window_by_url("index.html")
            client.close_other_windows()
            suite.check("close_other_windows", len(client.get_window_handles()) == 1 and "fixture" in client.get_title())
        suite.run("windows", windows)

        def waits():
            client.go_and_wait_for_load(url("index.html"))
            suite.check("wait_for_text", client.wait_for_text('//span[@id="later"]', "ready"))
            suite.check("wait_for_attribute", client.wait_for_attribute('//span[@id="later"]', "data-state", "ready"))
            suite.check("wait_for_element_count", client.wait_for_element_count('//ul[@id="count"]/li', 3))
            suite.check("wait_for_visible", client.wait_for_visible('//div[@id="appears"]'))
            suite.check("wait_for_invisible", client.wait_for_invisible('//div[@id="disappears"]'))
            suite.check("wait_for_element", client.wait_for_element('//p[@id="hidden"]'))
            suite.check("wait_for_url_contains", client.wait_for_url_contains("index.html"))
            suite.check("check_node_css_property", client.check_node_css_property('//p[@id="hidden"]', "display", r"(\w+)", "none") is True)
        suite.run("waits", waits)

        def page_change():
            root, old_url = client.get_page_root(), client.get_current_url()
            suite.check("click_and_wait_for_page_change", client.click_and_wait_for_page_change('//button[@id="btn-nav"]'))
            suite.check("arrived on page two", client.element_exists('//p[@id="arrived"]', timeout=2) and old_url != client.get_current_url())
            client.back()
            suite.check("back()", client.wait_for_title_contains("fixture", timeout=5))
            client.forward()
            suite.check("forward()", client.wait_for_title_contains("Page Two", timeout=5))
            client.go(url("index.html"))
            root, old_url = client.get_page_root(), client.get_current_url()
            client.js_click('//button[@id="btn-nav"]')
            suite.check("wait_for_page_change after a JS click", client.wait_for_page_change(root, old_url=old_url))
            client.go_and_wait_for_load(url("index.html"))
        suite.run("page change", page_change)

        def dialogs():
            client.find_and_click('//button[@id="btn-alert"]')
            suite.check("accept_alert", client.accept_alert() == "hello alert")
            client.find_and_click('//button[@id="btn-confirm"]')
            client.dismiss_alert()
            suite.check("dismiss_alert", client.get_text_from_node('//span[@id="confirm-result"]') == "cancel")
            client.find_and_click('//button[@id="btn-prompt"]')
            client.send_keys_to_alert("zed")
            suite.check("send_keys_to_alert", client.get_text_from_node('//span[@id="prompt-result"]') == "zed")
        suite.run("dialogs", dialogs)

        def mouse():
            client.hover('//div[@id="hoverme"]')
            suite.check("hover", client.wait_for_text('//div[@id="hoverme"]', "hovered", timeout=3))
            client.double_click('//div[@id="dbl"]')
            suite.check("double_click", client.wait_for_text('//div[@id="dbl"]', "double", timeout=3))
            client.right_click('//div[@id="ctx"]')
            suite.check("right_click", client.wait_for_text('//div[@id="ctx"]', "context", timeout=3))
            if browser != "firefox":
                # the context menu stays open in some builds; press Escape to be safe
                client.press_modifer_key("")
        suite.run("mouse", mouse)

        def screenshots():
            png = client.screenshot(str(download_dir / "viewport.png"))
            suite.check("screenshot", png.startswith(PNG_MAGIC) and (download_dir / "viewport.png").exists())
            suite.check("screenshot_element", client.screenshot_element('//h1[@id="title"]').startswith(PNG_MAGIC))
            full = client.screenshot_full_page(str(download_dir / "full.png"))
            suite.check("screenshot_full_page", full.startswith(PNG_MAGIC) and len(full) > len(png) * 0.5)
        suite.run("screenshots", screenshots)

        def upload():
            client.upload_file('//input[@id="file"]', str(FIXTURES / "data.bin"))
            suite.check("upload_file", client.wait_for_text('//span[@id="file-name"]', "data.bin", timeout=3))
        suite.run("upload", upload)

        def scrolling():
            client.go_and_wait_for_load(url("index.html"))
            started = time.monotonic()
            client.scroll_to_bottom(3)
            elapsed = time.monotonic() - started
            lazy = len(client.driver.find_elements("xpath", '//div[@id="lazy"]/p'))
            suite.check(f"scroll_to_bottom(3) loaded lazy items ({lazy}) in {elapsed:.1f}s", lazy >= 10 and elapsed < 3 * client.scroll_pause_time + 3)
            client.scroll_to_top()
            suite.check("scroll_to_top", client.execute_script("return window.scrollY;") == 0)
            client.scroll_to_element('//p[@id="bottom-marker"]')
            suite.check("scroll_to_element", client.execute_script("return window.scrollY;") > 0)
            client.scroll_to_bottom_watch_element_height(1, '//div[@id="lazy"]')
            suite.check("scroll_to_bottom_watch_element_height", True)
        suite.run("scrolling", scrolling)

        def login_flow():
            client.go_and_wait_for_load(url("index.html"))
            ok = client.login('//input[@id="user"]', "bob", '//input[@id="pass"]', "wrong", '//button[@id="login"]',
                              success_locator='//h1[@id="welcome"]', failure_locator='//div[@id="error"]', timeout=5)
            suite.check("login() reports a rejected password", ok is False and client.element_exists('//div[@id="error"]', timeout=1))
            ok = client.login('//input[@id="user"]', "bob", '//input[@id="pass"]', "secret", '//button[@id="login"]',
                              success_locator='//h1[@id="welcome"]', failure_locator='//div[@id="error"]', timeout=5)
            suite.check("login() succeeds", ok is True and client.get_title() == "Welcome")
        suite.run("login", login_flow)

        def cookies():
            profile = ProfileClient(client)
            cookie_file = download_dir / "cookies.json"
            calls = []

            def do_login():
                calls.append(1)
                client.go_and_wait_for_load(url("setcookie.html"))   # "logs in": the page sets session_token
                client.go_and_wait_for_load(url("index.html"))       # land where check_locator exists

            ok = profile.ensure_session(str(cookie_file), do_login, base_url=url("index.html"), check_locator='//h1[@id="title"]')
            suite.check("ensure_session logs in and saves cookies", ok and calls == [1] and cookie_file.exists())
            client.driver.delete_all_cookies()
            ok = profile.ensure_session(str(cookie_file), do_login, base_url=url("index.html"), check_locator='//h1[@id="title"]')
            suite.check("ensure_session restores from the cookie file", ok and calls == [1] and profile.cookie_exists("session_token"))
            suite.check("dump_cookies_to_file (pickle)", profile.dump_cookies_to_file(str(download_dir / "cookies.pkl")))
        suite.run("cookies", cookies)

        def logs_and_perf():
            client.go_and_wait_for_load(url("index.html"))
            logs = client.get_browser_logs()
            if browser in ("chrome", "edge"):
                suite.check("get_browser_logs captured console.error", any("fixture-error" in str(entry.get("message")) for entry in logs))
            else:
                suite.check("get_browser_logs returns [] where unsupported", logs == [])
            perf = PerformanceClient(client)
            perf.measure_page(url("page2.html"))
            suite.check("PerformanceClient.measure_page", perf.page_backend_performance is not None and perf.page_frontend_performance is not None and perf.page_backend_performance >= 0)
        suite.run("logs and performance", logs_and_perf)

        def download():
            if args.skip_download:
                return
            client.go_and_wait_for_load(url("index.html"))
            ignore = os.listdir(download_dir)
            client.find_and_click('//a[@id="dl"]')
            path = client.wait_for_download(str(download_dir), timeout=20, pattern="data.bin*", ignore=ignore)
            suite.check("wait_for_download", path is not None and Path(path).stat().st_size > 2000, str(path))
        suite.run("download", download)

        def misc():
            client.execute_script("window.__x = arguments[0] + arguments[1];", node=None, args=(1, 2))
            suite.check("execute_script with args and return", client.execute_script("return window.__x;") == 3)
            suite.check("execute_async_script", client.execute_async_script("var done = arguments[arguments.length - 1]; setTimeout(function () { done(5); }, 10);") == 5)
            client.set_timeouts(page_load=30, script=30)
            client.pause(0.05)
            client.pause((0.01, 0.02))
            client.maximize_window()
            suite.check("set_timeouts / pause / maximize_window", True)
        suite.run("misc", misc)

    suite.check("context manager quit the driver", client._closed or args.keep)

    if not args.skip_legacy:
        def legacy():
            from pylibselenium.driver import Chrome, ChromeOptions, Edge, EdgeOptions, Firefox, FirefoxOptions
            if browser == "chrome":
                driver = Chrome(executable_path="None", chrome_options=ChromeOptions(["--headless=new", "--no-sandbox"]).factory()).factory()
            elif browser == "edge":
                driver = Edge(options=EdgeOptions(["--headless=new", "--no-sandbox"])).factory()
            else:
                driver = Firefox(executable_path="None", firefox_options=FirefoxOptions(headless=True).factory()).factory()
            try:
                driver.get(url("page2.html"))
                suite.check("legacy executable_path/*_options constructors", driver.title == "Page Two")
            finally:
                driver.quit()
        suite.run("legacy constructors", legacy)

    return suite


def main():
    args = parse_args()
    if args.source:
        sys.path.insert(0, str(HERE.parent))
    import pylibselenium
    import pylibseleniummanagement
    from pylibseleniummanagement.driver.types import DROPDOWNTYPE as legacy_dropdown
    from pylibselenium.driver.types import DROPDOWNTYPE
    print(f"pylibselenium from {Path(pylibselenium.__file__).parent}")
    print(f"  alias package shares modules: {legacy_dropdown is DROPDOWNTYPE}")

    server, base_url = serve_fixtures()
    suites = []
    try:
        for browser in args.browser or ["chrome", "firefox"]:
            suites.append(run_browser(browser, base_url, args))
    finally:
        server.shutdown()

    print("\n=== summary ===")
    failed_total = 0
    for suite in suites:
        passed = len(suite.results) - len(suite.failed)
        failed_total += len(suite.failed)
        print(f"{suite.browser}: {passed}/{len(suite.results)} passed")
        for label, _, detail in suite.failed:
            print(f"  FAIL {label}: {detail}")
    sys.exit(1 if failed_total else 0)


if __name__ == "__main__":
    main()
