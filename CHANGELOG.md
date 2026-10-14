# Changelog

All notable changes to `pylibselenium`. Versions follow the `version` field in `pyproject.toml`.

## 0.5.0 - 2026-10-08

Efficiency, bug-fix and feature pass. Every public name from 0.4.0 still exists; see
"Behaviour changes" for the few things that act differently.

### Added

- `DriverClient.chrome(...)`, `.firefox(...)`, `.edge(...)` and `.remote(grid_url, browser=...)`
  build options, service, driver and client in one call. Selenium Manager resolves the driver when
  no `executable_path` is given.
- `with DriverClient(...) as client:` quits the browser on exit; `keep_open=True` leaves it open
  (instead of abusing `debug_mode` for that).
- Context managers `frame(target)`, `window(handle_or_index)` and `new_tab(url)` that switch and
  restore focus automatically.
- Windows: `wait_for_new_window`, `switch_to_window_by_title`, `switch_to_window_by_url`,
  `close_other_windows`; `switch_to_latest_window(previous_handles=...)` now waits for the new tab.
- Navigation: `back`, `forward`, `refresh` (alias of `reload`), `get_title`, `get_page_source`,
  `set_timeouts`, `pause(seconds | (low, high))`.
- Waits: `wait_for_visible`, `wait_for_invisible`, `wait_for_text`, `wait_for_attribute`,
  `wait_for_url_contains`, `wait_for_title_contains`, `wait_for_element_count`.
- Clicking: `try_click` (never raises), `js_click`, `click_elements_until_none`,
  `process_elements_until_none(locator, action)` for "delete every row" loops; `click_element`
  falls back to a JavaScript click when the pointer action cannot reach the element.
- Mouse: `hover`, `double_click`, `right_click`, `drag_and_drop`.
- Dialogs: `wait_for_alert`, `accept_alert`, `dismiss_alert`, `get_alert_text`, `send_keys_to_alert`.
- Forms: `upload_file`, `get_dropdown_options`, `get_selected_option`.
- Screenshots: `screenshot`, `screenshot_element`, `screenshot_full_page` (native on Firefox, CDP
  on Chromium).
- Logs and downloads: `get_browser_logs`, `get_performance_logs`, `wait_for_download`.
- `login(username_locator, username, password_locator, password, submit_locator, success_locator=,
  failure_locator=)` replaces the copy-pasted login blocks.
- `ProfileClient.ensure_session(cookie_file, login, base_url=, check_locator=)` loads cookies or
  logs in and saves them; `ProfileClient` accepts a `DriverClient`; non-`.pkl` cookie files are JSON.
- Every element method takes a trailing `timeout=` (seconds) that overrides `poll_time`.
- Options: `ChromeOptions`/`EdgeOptions` gained `headless`, `user_agent`, `proxy`, `window_size`,
  `download_dir`, `page_load_strategy`, `performance_logging`, `user_data_dir`, `profile_directory`;
  `FirefoxOptions` gained `headless`, `user_agent`, `proxy`, `download_dir`, `preferences`,
  `profile_directory`, `binary_path`. New `EdgeOptions`, `EdgeService`, `Edge`.
- Legacy constructor keywords are accepted again: `Chrome(executable_path=, chrome_options=)` and
  `Firefox(executable_path=, firefox_options=, firefox_profile=)`. A path that does not exist (or the
  literal string `"None"`) falls back to Selenium Manager with a warning.
- `pylibseleniummanagement` compatibility package: scripts that still import the old name work
  unchanged (`from pylibseleniummanagement.driver.types import DROPDOWNTYPE` etc.).
- `retry(..., backoff=, exceptions=)`, `retry_until_successful(..., max_attempts=)`.
- `MODIFERKEYS` members are now `str` subclasses (usable without `.value`); `MODIFIERKEYS` alias.
- `examples/smoke_test.py` + `examples/fixtures/`: headless Chrome/Firefox verification run.
- `Logger` is exported from the package root.

### Changed (efficiency)

- Every `find_*` / `get_*` / `click_*` method performs one `WebDriverWait` with one condition
  instead of a `presence` wait followed by a `clickable` wait on the same locator.
- `get_elements` and `click_all_elements*` wait for all elements in one condition
  (`AllElementsVisibleAndEnabled`: one `find_elements`, one `is_displayed` per element and one
  batched enabled check per poll) instead of one full `WebDriverWait` per element.
- `scroll_to_bottom` and `scroll_to_bottom_watch_element_height` poll the height every
  `poll_frequency` and stop as soon as it settles; `scroll_pause_time` is now the upper bound per
  scroll instead of a fixed sleep.
- Typed-text verification re-reads the value before retyping and stops immediately when the keys
  contain a key code such as `ENTER` (which never shows up in the value).
- `find_click_and_send_keys` clicks once instead of twice; `click_element_and_wait_for_load`
  shares one timeout budget between its two waits.
- `PerformanceClient` reads all timings in one script call (Navigation Timing Level 2 with a
  Level 1 fallback) and waits for the load event first.
- `set_attribute_of_node` / `remove_attribute_of_node` act on the element they already found
  instead of re-evaluating the XPath in JavaScript.
- `execute_script` / `execute_async_script` pass `node` and `args` as script arguments instead of
  interpolating values into the JavaScript source.
- The bot-detection script is installed with `Page.addScriptToEvaluateOnNewDocument`, so it
  survives navigations, and the user agent is derived from the real one instead of a Chrome/83 string.

### Behaviour changes

- `poll_frequency` defaults to `0.5` s (Selenium's own default) instead of `1` s: waits resolve up
  to half a second sooner at the cost of slightly more polling traffic.
- Chrome `performance` logging is off unless `ChromeOptions(performance_logging=True)`; the
  `browser` (console) log stays on.
- `action_delay` now really sleeps before every mutating action (navigate, click, type, scroll,
  switch), once per call even for composite methods. Reads (`get_*`, `wait_*`, `element_exists`)
  never sleep. Scripts that set `action_delay` will visibly slow down.
- `delete_profile=True` now acts: after `quit()` the session's profile directory is removed, but
  only when it is under the system temp directory or is the `user_data_dir` given to
  `DriverClient.chrome(...)`; anything else is left alone with a warning.
- `close_previous_sessions=True` quits other `DriverClient` instances created earlier in the same
  process (it never kills foreign browser processes).
- Driver, options and service factories raise after logging instead of printing and returning
  `None` when the browser cannot be started.
- `execute_script` returns the script's value by default (`return_value=True`).
- `check_throw` logs one line per failure; the traceback is only logged in `debug_mode`.
- `get_elements_until_none` returns `False` (instead of `None`) when nothing matched and `throw` is off.
- `get_text_from_node*`, `get_property_from_node` and `check_node_for_property` wait for the element
  to be present/visible rather than clickable, so disabled elements can be read.
- `find_and_send_keys_with_delay` honours `delay` (seconds, max random pause per key; default 0.1).
- `Directory` Windows paths were corrected (`%LOCALAPPDATA%` for Chrome/Edge, `%APPDATA%` for
  Firefox); `DEFAULT_LINUX_EDGE` is `~/.config/microsoft-edge`. `DEFAULT_LINUX_CHROME` is unchanged.

### Fixed

- `set_attribute_of_node` / `remove_attribute_of_node` referenced `locatorResult` instead of
  `XPathResult` and always failed.
- `check_node_css_property` called `.group()` on a list.
- `get_current_iframe` always returned `None` (the script had no `return`).
- `PerformanceClient` never populated its fields (`execute_script` discarded the values).
- `scroll_to_element` passed a string to `ActionChains.scroll_to_element`.
- `scroll_to_bottom_watch_element_height` read `.height` (undefined for most elements).
- `send_modifer_key_to_element` passed a `WebElement` to a locator-based condition.
- `find_and_send_keys_with_delay` ignored its `delay` argument.
- `WindowHandleToBeAvailableSwitchClosePrevious` closed the target window when it was already focused.
- `AppiumOptions.factory()` shadowed the Appium import and built the wrapper itself.
- `FirefoxOptions` called `options.add_extension`, which Selenium 4 does not have; add-ons are now
  installed after start-up through `driver.install_addon`.
- Service `log_path` was silently ignored by Selenium 4.47 (`log_output` is used; `log_path` is
  kept as an alias) and Safari `quiet` maps to `enable_logging`.
- `psutil` was imported but not declared, and a missing `psutil` or `appium` made the package call
  `exit()` on import. Both imports are optional at runtime and `psutil` is declared.
- 3.12-only f-string syntax under `requires-python >= 3.10`.
- Mutable default arguments in the options/preferences wrappers.
- `Logger` added its file handler twice, crashed on `log_file=None` and built a wrong path.
- `Error.__init__` did not call `super().__init__`, so `str(err)` was empty.
- Cookies saved from Firefox could not be loaded back: Firefox reports `sameSite: "None"` for cookies
  without the attribute and rejects re-adding them without `secure`; `ProfileClient` now drops that field.
- `click_chain_elements*` referenced an unbound `locator` in their error message.
- `CachedElement` printed every located element and silently swallowed exhausted retries.
- `packages` in `pyproject.toml` sat under `[project]`, where poetry-core ignores it.
- The README quickstart used a Selenium 3 constructor and a `Directory` member that did not exist.

## 0.4.0 - 2026-10-07

- Reliable "click, wait until the browser really left the page, then check elements" flow:
  `WaitForPageChange` (captured `<html>` root stale or fragment-stripped URL changed, then
  `readyState == complete`, then one settle poll) and `WaitForPageChangeAfterClick`.
- New client methods `get_page_root`, `get_current_url`, `wait_for_page_change`, `wait_for_url_change`,
  `click_and_wait_for_page_change`, `click_element_and_wait_for_page_change`, `element_does_not_exist`.
- `click_and_wait_for_html_load`, `click_element_and_wait_for_load` and `click_and_wait_for_load`
  rebuilt on the page-change primitive (no first-poll false positive, staleness counts as success).
- `wait_for_element_to_disappear(_by_xpath)` accept a string, a `(By, value)` tuple or a
  `WebElement`; `wait` is the timeout for the call (it used to be a per-poll sleep).
- `retry()` loop fixed; `_timeout` / `_wait` / `_locator` / `_perform_click` helpers introduced.

## 0.3.0 and earlier

- Appium support (`Appium`, `AppiumOptions`, `AppiumClient`).
- `Logger` helper.
- Initial Selenium facade: driver/options/service factories, `DriverClient`, `ProfileClient`,
  `PerformanceClient`, `Measure`, retry decorators.
