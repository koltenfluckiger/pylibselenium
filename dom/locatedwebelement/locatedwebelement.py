from selenium.webdriver.remote.webelement import WebElement


class LocatedWebElement(WebElement):
    def __init__(self, parent, id_, locator: tuple):
        super().__init__(parent, id_)
        self.locator = locator

    def get_locator(self):
        return self.locator
