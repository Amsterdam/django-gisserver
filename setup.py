#!/usr/bin/env python
import re
from pathlib import Path

from setuptools import find_packages, setup


def read(*parts):
    file_path = Path(__file__).parent.joinpath(*parts)
    with open(file_path) as f:
        return f.read()


def find_version(*parts):
    version_file = read(*parts)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return str(version_match.group(1))
    raise RuntimeError("Unable to find version string.")


tests_require = [
    "django-environ >= 0.4.5",
    "psycopg2-binary >= 2.8.4",
    "flake8 >= 3.7.9",
    "flake8-blind-except >= 0.1.1",
    "flake8-colors >= 0.1.6",
    "flake8-debugger >= 3.2.1",
    "flake8-raise >= 0.0.5",
    "pytest == 5.3.5",
    "pytest-django == 3.8.0",
    "pytest-cov == 2.8.1",
]


setup(
    name="django-gisserver",
    version=find_version("gisserver", "__init__.py"),
    license="Mozilla Public License 2.0 (MPL 2.0)",
    install_requires=["Django >= 2.0", "lxml >= 4.5.0", "ujson >= 1.35"],
    tests_require=tests_require,
    extras_require={"test": tests_require,},
    requires=["Django (>=2.0)"],
    description="Django speaking WFS 2.0 (exposing GeoDjango model fields)",
    long_description=read("README.md"),
    author="Diederik van der Boor",
    author_email="opensource@edoburu.nl",
    url="https://github.com/amsterdam/django-gisserver",
    packages=find_packages(exclude=("tests", "example*"), include=("gisserver",)),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Framework :: Django",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.0",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
