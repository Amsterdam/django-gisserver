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
    "lxml >= 4.9.1",
    "pytest >= 6.2.3",
    "pytest-django >= 4.1.0",
    "pytest-cov >= 2.11.1",
]

docs_require = [
    "Django ~= 5.1",
    "sphinxcontrib-django >= 2.5",
    "myst-parser >= 3.0.1",
    "psycopg2-binary >= 2.8.4",
]


setup(
    name="django-gisserver",
    version=find_version("gisserver", "__init__.py"),
    license="Mozilla Public License 2.0",
    install_requires=[
        "Django >= 4.2",
        "defusedxml >= 0.7.1",
        "lru_dict >= 1.1.7",
        "orjson >= 3.9.15",
        "pyproj >= 3.6.1",
    ],
    extras_require={
        "tests": tests_require,
        "docs": docs_require,
    },
    requires=["Django (>=4.2, >=5.1)"],
    description="Django speaking WFS 2.0 (exposing GeoDjango model fields)",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Diederik van der Boor",
    author_email="opensource@edoburu.nl",
    url="https://github.com/amsterdam/django-gisserver",
    packages=find_packages(exclude=("tests*", "example*"), include=("gisserver*")),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.1",
        "Framework :: Django :: 5.2",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
)
