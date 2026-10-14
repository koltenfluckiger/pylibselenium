"""Page timing measurements through the Navigation Timing API."""
import logging

from ..driver.client import DriverClient
from ..driver.wait import WaitForPageLoad

logger = logging.getLogger(__name__)

# One round trip for every value. Navigation Timing Level 2 (``PerformanceNavigationTiming``)
# reports milliseconds relative to ``timeOrigin``; the Level 1 fallback reports epoch
# milliseconds. The differences computed below are the same either way.
_TIMING_JS = """
var nav = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
var t = nav || performance.timing;
return {
    start: nav ? 0 : t.navigationStart,
    loaded: t.domContentLoadedEventEnd,
    ended: t.loadEventEnd,
    complete: document.readyState === 'complete'
};
"""


class PerformanceClient(object):
    """
    Backend (navigation start -> DOMContentLoaded) and frontend (DOMContentLoaded -> load event)
    timings of the current page, in milliseconds.

    ``measure()`` fills ``backend_performance`` / ``frontend_performance``; ``measure_page(url)``
    navigates first and fills ``page_backend_performance`` / ``page_frontend_performance``.
    Getters return None until a measurement succeeded.
    """

    def __init__(self, client: DriverClient) -> None:
        self.client = client
        self.start = None
        self.loaded = None
        self.ended = None
        self.backend_performance = None
        self.frontend_performance = None
        self.page_backend_performance = None
        self.page_frontend_performance = None

    def _timings(self) -> dict:
        """Wait for the load event (so ``loadEventEnd`` is populated) and read every timing in one script call."""
        self.client._wait().until(WaitForPageLoad())
        data = self.client.execute_script(_TIMING_JS)
        if not data or not data.get("complete"):
            raise RuntimeError("the page has not finished loading")
        return data

    def measure(self) -> None:
        """Measure the page that is currently open."""
        try:
            data = self._timings()
            self.start, self.loaded, self.ended = data["start"], data["loaded"], data["ended"]
            self.backend_performance = self.loaded - self.start
            self.frontend_performance = self.ended - self.loaded
        except Exception as err:
            self.client._fail("Failed to measure the page timings.", err)

    def measure_page(self, url: str) -> None:
        """Navigate to ``url`` and measure it."""
        try:
            self.client.go(url)
            data = self._timings()
            self.start, self.loaded, self.ended = data["start"], data["loaded"], data["ended"]
            self.page_backend_performance = self.loaded - self.start
            self.page_frontend_performance = self.ended - self.loaded
        except Exception as err:
            self.client._fail(f"Failed to measure the page timings of {url}.", err)

    def as_dict(self) -> dict:
        """All measured values in one mapping."""
        return {
            "backend_performance": self.backend_performance,
            "frontend_performance": self.frontend_performance,
            "page_backend_performance": self.page_backend_performance,
            "page_frontend_performance": self.page_frontend_performance,
        }

    def get_backend_performance(self):
        return self.backend_performance

    def get_frontend_performance(self):
        return self.frontend_performance

    def get_page_backend_performance(self):
        return self.page_backend_performance

    def get_page_frontend_performance(self):
        return self.page_frontend_performance

    # camelCase names kept for existing callers
    getBackendPerformance = get_backend_performance
    getFrontPerformance = get_frontend_performance
    getPageBackendPerformance = get_page_backend_performance
    getPageFrontPerformance = get_page_frontend_performance
