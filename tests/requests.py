from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, ClassVar

import pytest
from django.test import Client

from gisserver.parsers import ows
from tests.utils import WFS_20_AND_GML_XSD, validate_xsd


class Url(Enum):
    NORMAL = "/v1/wfs/"
    FLAT = "/v1/wfs-flattened/"
    COMPLEX = "/v1/wfs-complextypes/"
    GENERATED = "/v1/wfs-gen-field/"

    def __str__(self):
        # Python 3.11+ has StrEnum for this.
        return self.value


@dataclass
class Request:
    url: Url | None
    id: str | None
    expect: Any | None

    def __init__(self, *, id=None, expect=None, url: Url | None = None):
        self.id = id
        self.expect = expect
        self.url = url

    def test_id(self):
        method = self.__class__.__name__.upper()
        prefix = method if not self.id else f"{method}-{self.id}"
        if self.url is not None:
            return f"{prefix}-{self.url.name}"
        else:
            return prefix

    def get_ows_request(self) -> ows.BaseOwsRequest:
        raise NotImplementedError()

    def get_response(self, client: Client):
        raise NotImplementedError()


@dataclass
class Get(Request):
    method: ClassVar[str] = "GET"
    query: str | Callable

    def __init__(self, query, **kwargs):
        super().__init__(**kwargs)
        self.query = query

    def get_ows_request(self) -> ows.BaseOwsRequest:
        return ows.parse_get_request(
            self.query,
            ns_aliases={
                # For now, have similar namespaces as the XML_NS constant.
                # Should allow to resolve both unprefixed QName and app: prefixes.
                # To test the KVP parser namespace handling, write a test specifically for that.
                "": "http://example.org/gisserver",
                "app": "http://example.org/gisserver",
            },
        )

    def get_response(self, client: Client):
        if isinstance(self.query, str):
            return client.get(f"{self.url}{self.query}")
        else:
            # a function is being passed in.
            def func(*args):
                q = self.query(*args)
                return client.get(f"{self.url}{q}")

            return func


@dataclass
class Post(Request):
    method: ClassVar[str] = "POST"
    body: str | Callable
    query: str | Callable | None
    validate_xml: bool

    def __init__(self, body, query=None, validate_xml: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.body = body
        self.query = query
        self.validate_xml = validate_xml

    def get_ows_request(self) -> ows.BaseOwsRequest:
        if self.validate_xml:
            validate_xsd(self.body, WFS_20_AND_GML_XSD)
        return ows.parse_post_request(self.body)

    def get_response(self, client: Client):
        if isinstance(self.body, str):
            if self.validate_xml:
                validate_xsd(self.body, WFS_20_AND_GML_XSD)
            return client.post(
                f"{self.url}{self.query}" if self.query else self.url.value,
                data=self.body,
                content_type="application/xml",
            )
        else:
            # a function is being passed in.
            def func(*args):
                b = self.body(*args)
                q = self.query(*args) if self.query else ""
                if self.validate_xml:
                    validate_xsd(b, WFS_20_AND_GML_XSD)
                return client.post(f"{self.url}{q}", data=b, content_type="application/xml")

            return func


# Decorator
def parametrize_response(*param_values: Request, url: Url | None = None):
    """This is a decorator that wraps the parametrizing of "response", and allows us to
    set global flags (used for getting the correct url).

    Usage::

        @parametrize_response(
            Get("?query=test"),
            Get(lambda id: f"?query=test{id}", url=Url.COMPLEX),
            Post("<xml></xml>"),
            Post("<xml></xml>", expect=AssertionError),
            url=Url.FLAT,
        )
        def test_function(response):
            ...

    Note that each Request value can also take its own url, although you can also pass in
    a global url as in the above example.

    Requests (Get, Post) either get a string query/body argument or a Callable, which can be used
    later in the testing function to perform different requests at different times in the test.
    In this case, you need to call the response() to get an actual response object in your test.

    The ``response`` fixture also receives a ``params`` that references the original parameters,
    and it will get an ``expect`` value when that is set.

    NB: When your response depends on other fixtures (for example because you need to have
    some rows in the database), ensure the `response` fixture argument comes at the end of the
    testing function arguments.
    """
    for request in param_values:
        if request.url is None:
            request.url = url or Url.NORMAL

    # Return the decorator which will be called with the original function that has a 'response' fixture.
    return pytest.mark.parametrize(
        "response",
        param_values,
        indirect=True,
        ids=[val.test_id() for val in param_values],
    )


def parametrize_ows_request(*requests: Request):
    """A decorator for parametrizing the "ows_request".
    This allows testing whether GET and POST requests have the same parsing.

    Usage::

        @parametrize_ows_request(
            Get("?query=test"),
            Get(lambda id: f"?query=test{id}"),
            Post("<xml></xml>"),
            Post("<xml></xml>", expect=AssertionError),
        )
        def test_function(ows_request):
            ...
    """
    # Return the decorator which will be called with the original function that has a 'response' fixture.
    return pytest.mark.parametrize(
        "ows_request",
        requests,
        indirect=True,
        ids=[val.test_id() for val in requests],
    )
