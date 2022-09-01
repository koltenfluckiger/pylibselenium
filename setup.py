from setuptools import find_packages
from setuptools import setup

setup(
    name='pylibseleniummanagement',
    version='0.0.1',
    packages=find_packages('profile', 'driver', 'performance'),
    url='https://github.com/koltenfluckiger/pylibseleniummanagement',
    license='MIT',
    author='Kolten Fluckiger',
    author_email='wrtunder@gmail.com',
    description='Manager and interface for using Selenium to make it easier to do certain actions without lines and lines of code.'
)
