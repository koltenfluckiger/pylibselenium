from typing import List

from selenium.webdriver.firefox.firefox_profile import FirefoxProfile


class FirefoxPreferences(object):

    def __init__(self, arguments: List[tuple] = None, directory=None):
        self.arguments = list(arguments or [])
        self.directory = directory

    def factory(self) -> FirefoxProfile:
        firefox_profile = FirefoxProfile(profile_directory=self.directory)
        for pref, value in self.arguments:
            firefox_profile.set_preference(pref, value)
        self.firefox_profile = firefox_profile
        return firefox_profile
