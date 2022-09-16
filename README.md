<!-- PROJECT SHIELDS -->

<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

  <h3 align="center">Selenium Managment</h3>

  <p align="center">
    Use this python package to help interact with the Selenium webdriver. This allows for ease of use and performance measuring.
    <br />
    <a href="https://github.com/koltenfluckiger/pylibseleniummanagement"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/koltenfluckiger/pylibseleniummanagement">View Demo</a>
    ·
    <a href="https://github.com/koltenfluckiger/pylibseleniummanagement/issues">Report Bug</a>
    ·
    <a href="https://github.com/koltenfluckiger/pylibseleniummanagement/issues">Request Feature</a>
  </p>
</p>

<!-- TABLE OF CONTENTS -->

<details open="open">
  <summary><h2 style="display: inline-block">Table of Contents</h2></summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->

## About The Project

This python package allows for ease of use to complete and manipulate the Selenium Webdriver.

### Built With

-   [Selenium](https://pypi.org/project/selenium/)
-   [Python3](https://www.python.org/)

<!-- GETTING STARTED -->

## Getting Started

To get a local copy up and running follow these simple steps.

### Prerequisites

This is an example of how to list things you need to use the software and how to install them.

-   bash
    ```sh
    sudo apt install -y python3 python3-pip
    pip3 install selenium pickle
    ```

### Installation

1.  Clone the repo
    ```sh
    git clone https://github.com/taosdevops/pylibseleniummanagement.git
    ```
2.  Install PIP package
    ```sh
    pip3 install -e pylibseleniummanagement
    ```

<!-- USAGE EXAMPLES -->

## Usage

Use this space to show useful examples of how a project can be used. Additional screenshots, code examples and demos work well in this space. You may also link to more resources.


```python
from pylibseleniummanagement.driver import Chrome, Directory, DriverClient, ChromeOptions
from pylibseleniummanagement.profile import ProfileClient
from pylibseleniummanagement.performance import Measure

@Measure
def main():
        chrome_options = ChromeOptions(["--user-data-dir={}".format(Directory.WIN_CHROME.value)])
        chrome_opts = chrome_options.factory()
        chrome_driver = Chrome(executable_path="chromedriver.exe", chrome_options=chrome_opts)
        chrome_driver = chrome_driver.factory()
        chrome_client = DriverClient(chrome_driver, poll_time=10, poll_frequency=1)
        profile_client = ProfileClient(chrome_driver)

        chrome_client.go("https://facebook.com")

        chrome_client.find_click_and_send_keys('//input[@name="email"]',"XXXXXXXX@gmail.com")
        chrome_client.find_click_and_send_keys('//input[@name="pass"]',"XXXXXXXXXXXX")
        chrome_client.find_and_click('//button[@name="login"]')

if __name__ == '__main__':
    # We can get the execution time of the entire function with the decorator
    main()
    print(main.elasped)
```


<!-- ROADMAP -->

## Roadmap

See the [open issues](https://github.com/koltenfluckiger/pylibseleniummanagement/issues) for a list of proposed features (and known issues).

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

Project Link: <https://github.com/koltenfluckiger/pylibseleniummanagement>

<!-- MARKDOWN LINKS & IMAGES -->

<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[contributors-shield]: https://img.shields.io/github/contributors/koltenfluckiger/repo.svg?style=for-the-badge

[contributors-url]: https://github.com/koltenfluckiger/pylibseleniummanagement/graphs/contributors

[forks-shield]: https://img.shields.io/github/forks/koltenfluckiger/repo.svg?style=for-the-badge

[forks-url]: https://github.com/koltenfluckiger/pylibseleniummanagement/network/members

[stars-shield]: https://img.shields.io/github/stars/koltenfluckiger/repo.svg?style=for-the-badge

[stars-url]: https://github.com/koltenfluckiger/pylibseleniummanagement/stargazers

[issues-shield]: https://img.shields.io/github/issues/koltenfluckiger/repo.svg?style=for-the-badge

[issues-url]: https://github.com/koltenfluckiger/pylibseleniummanagement/issues

[license-shield]: https://img.shields.io/github/license/koltenfluckiger/repo.svg?style=for-the-badge

[license-url]: https://github.com/koltenfluckiger/pylibseleniummanagement/blob/master/LICENSE.txt

[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555

[linkedin-url]: https://linkedin.com/in/koltenfluckiger
