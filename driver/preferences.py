
from typing import List
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile


class FirefoxPreferences(object):

    def __init__(self, arguments: List[tuple] = [], directory=None):
        self.arguments = arguments
        self.directory = directory

    def factory(self) -> FirefoxProfile:
        try:
            firefox_profile = FirefoxProfile(profile_directory=self.directory)
            for arg in self.arguments:
                pref = arg[0]
                value = arg[1]
                firefox_profile.set_preference(pref, value)
            self.firefox_profile = firefox_profile
            return firefox_profile
        except Exception as err:
            print(err)
