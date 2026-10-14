
[contributors-url]: <https://img.shields.io/github/contributors/koltenfluckiger/pylibselenium?style=for-the-badge>
[forks-url]: <https://img.shields.io/github/forks/koltenfluckiger/pylibselenium?style=for-the-badge>
[stars-url]: <https://img.shields.io/github/stars/koltenfluckiger/pylibselenium?style=for-the-badge>
[issues-url]: <https://img.shields.io/github/issues/koltenfluckiger/pylibselenium?style=for-the-badge>
[linkedin-shield]: <https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555>
[linkedin-url]: <https://linkedin.com/in/koltenfluckiger>

![Contributors][contributors-url]
![Forks][forks-url]
![Stargazers][stars-url]
![Issues][issues-url]
![LinkedIn][linkedin-shield]

  <h3 align="center">pylibselenium</h3>

  <p align="center">
    A facade over Selenium WebDriver for browser automation scripts: one-call browser start-up,
    resilient find/click/type helpers, real page-change detection, frames, tabs, dialogs, cookies
    and timing, with a consistent error policy.
    <br />
    <a href="https://github.com/koltenfluckiger/pylibselenium"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/koltenfluckiger/pylibselenium">View Demo</a>
    ·
    <a href="https://github.com/koltenfluckiger/pylibselenium/issues">Report Bug</a>
    ·
    <a href="https://github.com/koltenfluckiger/pylibselenium/issues">Request Feature</a>
  </p>
</p>

<!-- TABLE OF CONTENTS -->

<details open="open">
  <summary><h2 style="display: inline-block">Table of Contents</h2></summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#getting-started">Getting Started</a></li>
    <li><a href="#quickstart">Quickstart</a></li>
    <li><a href="#configuring-the-client">Configuring the client</a></li>
    <li><a href="#browser-options">Browser options</a></li>
    <li><a href="#what-the-client-can-do">What the client can do</a></li>
    <li><a href="#locators-errors-and-timeouts">Locators, errors and timeouts</a></li>
    <li><a href="#cookies-timing-retries-and-logging">Cookies, timing, retries and logging</a></li>
    <li><a href="#performance-notes">Performance notes</a></li>
    <li><a href="#upgrading">Upgrading</a></li>
    <li><a href="#verifying-a-change">Verifying a change</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->

## About The Project

`pylibselenium` wraps Selenium 4 so an automation script reads as a list of intentions
(`find_click_and_send_keys`, `click_and_wait_for_page_change`, `login`, ...) instead of a list of
waits. Every method performs exactly one `WebDriverWait`, honours a per-call `timeout`, and either
returns a falsy value or raises `pylibselenium.Error` depending on how the client was built.

### Built With

-   [Selenium](https://pypi.org/project/selenium/) 4.35 or newer
-   [Python](https://www.python.org/) 3.10 or newer
-   [psutil](https://pypi.org/project/psutil/) (driver process clean-up) and
    [Appium-Python-Client](https://pypi.org/project/Appium-Python-Client/) (mobile sessions)

<!-- GETTING STARTED -->

## Getting Started

### Prerequisites

A supported browser (Chrome, Edge, Firefox or Safari). You do **not** need to download a driver:
Selenium Manager fetches a chromedriver/geckodriver/msedgedriver that matches the installed browser
the first time a session starts. If an old driver is on your `PATH`, remove it from the `PATH` or
pass `executable_path=` explicitly.

### Installation

```sh
git clone https://github.com/koltenfluckiger/pylibselenium.git
cd pylibselenium
make all            # poetry build + uv pip install dist/*.whl
# or, by hand:
poetry build && pip install dist/pylibselenium-0.5.0-py3-none-any.whl
# editable during development:
pip install -e .
```

## Quickstart

```python
from pylibselenium import DriverClient

with DriverClient.chrome(headless=True, poll_time=10) as client:
    client.go_and_wait_for_load("https://example.com/login")
    client.find_click_and_send_keys('//input[@name="email"]', "me@example.com")
    client.find_click_and_send_keys('//input[@name="pass"]', "secret")
    if not client.click_and_wait_for_page_change('//button[@name="login"]', timeout=30):
        raise SystemExit("the login click did not navigate")
    if client.element_does_not_exist('//div[@role="alert"]', timeout=5):
        print("logged in:", client.get_title())
```

The browser is quit when the `with` block ends (also on exceptions). `DriverClient.firefox(...)`,
`DriverClient.edge(...)` and `DriverClient.remote(grid_url, browser="chrome")` work the same way.

The explicit three-step form is still available when you need full control over the Selenium
objects:

```python
from pylibselenium.driver import Chrome, ChromeOptions, ChromeService, DriverClient, RemoteWebdriver

options = ChromeOptions(arguments=["--disable-notifications"], headless=True, download_dir="/tmp/dl")
driver = Chrome(service=ChromeService(), options=options).factory()      # wrappers or raw Selenium objects
client = DriverClient(driver, poll_time=10, poll_frequency=0.5, throw=True)

# Selenium Grid
driver = RemoteWebdriver("grid.example.com:4444", options=options).factory()   # scheme added for you
```

A ready-made login helper covers the fill/fill/click/wait block most scripts repeat:

```python
ok = client.login('//input[@id="user"]', user, '//input[@id="pass"]', password, '//button[@id="login"]',
                  success_locator='//nav[@id="account"]', failure_locator='//div[@id="error"]')
```

## Configuring the client

`DriverClient(driver, ...)` keyword arguments (all optional):

| Argument | Default | Meaning |
|---|---|---|
| `poll_time` | `10` | Seconds to wait for an element or condition. Every method also takes a per-call `timeout=`. |
| `poll_frequency` | `0.5` | Seconds between condition checks. |
| `scroll_pause_time` | `5` | Upper bound, in seconds, for the page to grow after each scroll in `scroll_to_bottom`. |
| `throw` | `False` | `True`: failures raise `pylibselenium.Error`. `False`: failures are logged and a falsy value is returned. |
| `debug_mode` | `False` | Do not quit the browser automatically and log tracebacks for swallowed errors. |
| `keep_open` | `False` | Do not quit the browser when the client is deleted or leaves a `with` block. |
| `action_delay` | `0` | Seconds to sleep before every mutating action (click, type, navigate, scroll, switch); reads never sleep. |
| `delete_profile` | `False` | Remove the profile directory after `quit()`. Only a temporary profile or the `user_data_dir` passed to `DriverClient.chrome()` is ever removed. |
| `close_previous_sessions` | `False` | Quit other `DriverClient` instances created earlier in this process. |
| `disable_bot_detection_flag` | `False` | Hide `navigator.webdriver` and friends through CDP (Chromium browsers). |
| `default_by` | `By.XPATH` | Locator strategy paired with bare locator strings. |

`DriverClient.chrome/edge/firefox/remote(...)` accept the same keywords plus the browser options below.

## Browser options

`ChromeOptions` / `EdgeOptions`: `arguments`, `preferences`, `extension_paths`, `binary_path`,
`disable_bot_detection_flag`, `debug_mode`, `headless`, `user_agent`, `proxy`, `window_size`,
`download_dir`, `page_load_strategy`, `performance_logging` (off by default), `user_data_dir`,
`profile_directory`.

`FirefoxOptions`: `arguments`, `extension_paths` (installed after start-up with `install_addon`),
`headless`, `user_agent`, `proxy`, `download_dir`, `preferences`, `profile_directory`, `binary_path`.

`ChromeService` / `EdgeService` / `FirefoxService(executable_path=None, log_output=None)`: leave
`executable_path` empty for Selenium Manager; `log_output` is a file path or stream for the driver log.

The driver factories (`Chrome`, `Edge`, `Firefox`, `Safari`, `RemoteWebdriver`, `Appium`) accept
either the wrappers above or raw Selenium objects, and still accept the legacy keywords
`Chrome(executable_path=, chrome_options=)` and `Firefox(executable_path=, firefox_options=, firefox_profile=)`.

## What the client can do

Every method takes a locator (see below) and an optional `timeout=` unless noted.

| Area | Methods |
|---|---|
| Navigation | `go`, `go_and_wait_for_load`, `reload` / `refresh`, `back`, `forward`, `get_title`, `get_current_url`, `get_page_source`, `set_timeouts`, `maximize_window`, `pause` |
| Finding | `get_element`, `get_elements`, `get_elements_until_none`, `try_to_get_element`, `get_child_element`, `get_element_relative`, `get_element_by_tag_name`, `element_exists`, `element_does_not_exist` |
| Clicking | `find_and_click`, `click_element`, `try_to_click_element`, `try_click`, `js_click`, `click_all_elements`, `click_all_elements_and_scroll`, `click_all_elements_and_reload`, `click_chain_elements`, `click_chain_elements_infinitely`, `click_elements_until_none`, `process_elements_until_none` |
| Click and wait | `click_and_wait_for_page_change`, `click_element_and_wait_for_page_change`, `click_and_wait_for_element`, `click_and_wait_for_html_load`, `click_and_wait_for_load`, `click_element_and_wait_for_load`, `find_and_click_and_wait_for_element` |
| Typing | `find_and_send_keys`, `find_and_send_keys_with_delay`, `find_click_and_send_keys`, `find_click_and_send_keys_and_go`, `find_and_send_modifer_key`, `press_modifer_key`, `press_modifer_key_send_keys`, `press_modifer_key_on_element`, `press_modifer_key_send_keys_on_element`, `send_modifer_key`, `send_modifer_key_to_element`, `send_modifer_key_to_window` |
| Waiting | `wait_for_element`, `wait_for_visible`, `wait_for_invisible`, `wait_for_text`, `wait_for_attribute`, `wait_for_element_count`, `wait_for_element_to_disappear`, `wait_for_element_to_disappear_by_xpath`, `wait_for_url_contains`, `wait_for_url_change`, `wait_for_title_contains`, `wait_for_page_change`, `get_page_root`, `wait_to_click_element`, `check_element_for_value_change` |
| Reading the DOM | `get_text_from_node`, `get_text_from_node_convert`, `get_text_from_node_element`, `get_attribute_from_node`, `get_property_from_node`, `get_inner_html_from_node`, `get_outer_html_from_node`, `check_node_for_property`, `check_node_css_property`, `set_attribute_of_node`, `remove_attribute_of_node`, `execute_script`, `execute_async_script` |
| Forms | `select_option_from_dropdown`, `get_dropdown_options`, `get_selected_option`, `upload_file`, `login` |
| Frames | `frame(target)` context manager, `find_frame_switch`, `switch_to_iframe`, `switch_to_default_iframe`, `switch_to_parent_frame`, `get_current_iframe` |
| Tabs and windows | `new_tab(url)` and `window(handle_or_index)` context managers, `open_new_tab`, `open_new_tab_go`, `wait_for_new_window`, `switch_to_latest_window`, `switch_to_first_window`, `switch_to_window_by_title`, `switch_to_window_by_url`, `find_window_handle_switch_to_it`, `find_window_handle_switch_to_it_close_previous`, `close_current_window`, `close_other_windows`, `get_window_handles`, `get_current_window_handle`, `get_window_handle_id` |
| Mouse | `hover`, `double_click`, `right_click`, `drag_and_drop`, `scroll_to_element`, `scroll_to_top`, `scroll_to_bottom`, `scroll_to_bottom_watch_element_height` |
| Dialogs | `wait_for_alert`, `accept_alert`, `dismiss_alert`, `get_alert_text`, `send_keys_to_alert` |
| Screenshots, logs, downloads | `screenshot`, `screenshot_element`, `screenshot_full_page`, `get_browser_logs`, `get_performance_logs`, `wait_for_download` |
| Lifecycle | `with client:`, `quit`, `close`, `DriverClient.chrome/edge/firefox/remote` |

### Waiting for a page change

Use `click_and_wait_for_page_change` when a click is expected to take the browser to a different page. It
clicks, waits until the document was replaced (or the URL changed for single-page apps), waits for the new
page to finish loading, and only then returns. `element_exists` / `element_does_not_exist` then gate the next
step with an explicit timeout and never raise.

```python
if not client.click_and_wait_for_page_change('//button[@name="login"]', timeout=30):
    raise SystemExit("the login click did not navigate")

if client.element_exists('//input[@name="pass"]', timeout=5):
    raise SystemExit("still on the login form")

if client.element_does_not_exist('//div[@role="alert"]', timeout=10):
    print("logged in, no error banner")
```

If the navigation is triggered some other way (pressing Enter, submitting with JavaScript), capture the page
first and wait on it afterwards:

```python
root, url = client.get_page_root(), client.get_current_url()
client.press_modifer_key(MODIFERKEYS.ENTER)
client.wait_for_page_change(root, old_url=url, timeout=30)
```

### Frames, tabs and "until none remain"

```python
with client.frame('//iframe[@id="gsft_main"]'):
    client.find_and_click('//button[@id="accept"]')          # back in the parent frame afterwards

with client.new_tab("https://mail.example.com") as handle:
    code = client.get_text_from_node('//span[@id="otp"]')  # tab is closed and focus restored afterwards

deleted = client.click_elements_until_none('//table//button[@aria-label="Delete"]')
client.try_click('//button[text()="Not now"]', timeout=2)  # optional step, never raises
```

## Locators, errors and timeouts

- A locator is a bare string paired with `default_by` (XPath unless you change it), a `(By, value)`
  tuple such as `LocatedWebElement.get_locator()`, or, where documented, an already located `WebElement`.
- `throw=False` (default): failures are logged once through the `pylibselenium.driver.client` logger
  and the method returns `None` (getters), `False` (`try_to_get_element`, `get_elements_until_none`,
  the `wait_*`/`click_and_wait_*` family) or `0`. `throw=True`: the same failures raise `pylibselenium.Error`.
- `element_exists`, `element_does_not_exist`, `try_click` and `try_to_get_element` never raise and never
  log an error; they are meant for branching.
- Context managers (`frame`, `window`, `new_tab`) raise when they cannot enter, regardless of `throw`,
  and never raise while restoring focus.
- `timeout=` on any method overrides `poll_time` for that call; `timeout=0` checks once.

## Cookies, timing, retries and logging

```python
from pylibselenium import ProfileClient, PerformanceClient, Measure, retry, retry_until_successful, Logger

profile = ProfileClient(client)                     # or ProfileClient(driver)
profile.ensure_session("cookies.json",             # .pkl keeps using pickle; anything else is JSON
                       login=lambda: client.login(...),
                       base_url="https://example.com",
                       check_locator='//nav[@id="account"]')
profile.dump_cookies_to_file("cookies.json")       # only when the cookies look fresh and auth-related

perf = PerformanceClient(client)
perf.measure_page("https://example.com")           # one script call: Navigation Timing Level 2
print(perf.page_backend_performance, perf.page_frontend_performance)   # milliseconds

@Measure
def main(): ...
main(); print(main.elapsed)                        # seconds

@retry(retries=3, delay=1, backoff=2)              # or @retry_until_successful(delay=10, max_attempts=50)
def step(): ...

log = Logger("my-script", "/tmp/my-script.log").get_logger()   # console + file, handlers added once
```

## Performance notes

Each WebDriver command is an HTTP round trip to the driver, so the client is designed around doing
as few as possible per operation:

| Operation | Commands per poll before 0.5.0 | Now |
|---|---|---|
| `find_and_click` | presence (1) + clickable (3) + click (1) = 5 | clickable (3) + click (1) = 4 |
| `get_elements` with N matches | (1 + N) + N separate clickable waits (2 each) | 1 + N + 1 batched enabled check |
| `find_and_send_keys` | 3 + 6 per verification poll | 3 + 5 on the first poll, 2 on re-polls |
| `scroll_to_bottom` | fixed 5 s sleep per scroll | polls every `poll_frequency`, stops when the height settles |
| `PerformanceClient.measure` | 3 scripts (and the result was lost) | 1 script |

Keep `set_timeouts(implicit=...)` at zero: an implicit wait is added to every explicit wait the client performs.

## Upgrading

### From 0.4.0

All 0.4.0 names still exist. Behaviour that changed on purpose:

- `poll_frequency` defaults to `0.5` s (was `1`).
- Chrome `performance` logging is opt-in: `ChromeOptions(performance_logging=True)`.
- `action_delay` now really sleeps before mutating actions; scripts that set it will slow down accordingly.
- `delete_profile=True` now removes temporary profiles after `quit()` (guarded, see the table above).
- Driver/options/service factories raise instead of printing and returning `None`.
- `execute_script` returns the script's value by default.

See `CHANGELOG.md` for the full list, including the bugs that were fixed.

### From `pylibseleniummanagement`

Scripts that still `import pylibseleniummanagement` keep working: the wheel ships a package of that
name which re-exports `pylibselenium` and shares its modules. The pre-Selenium-4 constructor
keywords (`Chrome(executable_path=, chrome_options=)`, `Firefox(executable_path=, firefox_options=,
firefox_profile=)`) are accepted; a driver path that does not exist falls back to Selenium Manager.

## Verifying a change

There is no unit-test suite; the package is verified against real browsers:

```sh
make smoke                                   # headless Chrome + Firefox against examples/fixtures
python examples/smoke_test.py --browser chrome --source   # import the checkout instead of the installed wheel
```

The run prints PASS/FAIL per case (finds, clicks, typing with key codes, page change, frames, tabs,
dialogs, screenshots, uploads, downloads, dropdowns, scrolling, `login`, `ensure_session`, logs,
the legacy constructors and the alias package) and the number of WebDriver commands the core
operations cost.

<!-- ROADMAP -->

## Roadmap

- Mirror the 0.5.0 changes into `pylibzen` (the Zendriver twin of this package).
- Network capture through WebDriver BiDi instead of the Chromium performance log.
- Optional `undetected-chromedriver` backend behind the same `DriverClient.chrome()` call.
- Explicit `DriverClient.kill_orphaned_drivers()` for browsers left behind by earlier runs.
- An async client sharing the wait conditions.

See the [open issues](https://github.com/koltenfluckiger/pylibselenium/issues) for a list of proposed features (and known issues).

<!-- CONTRIBUTING -->

## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

<!-- LICENSE -->

## License

Distributed under the MIT License. See `LICENSE` for more information.

<!-- CONTACT -->

## Contact

Project Link: <https://github.com/koltenfluckiger/pylibselenium>
