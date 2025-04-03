from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import pytest
from django.test import Client


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

    def get_response(self, client: Client):
        raise NotImplementedError()


@dataclass
class Get(Request):
    query: str | Callable

    def __init__(self, query, **kwargs):
        super().__init__(**kwargs)
        self.query = query

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
    body: str | Callable

    def __init__(self, body, **kwargs):
        super().__init__(**kwargs)
        self.body = body

    def get_response(self, client: Client):
        if isinstance(self.body, str):
            return client.post(self.url, data=self.body, content_type="application/xml")
        else:
            # a function is being passed in.
            def func(*args):
                b = self.body(*args)
                return client.post(self.url, data=b, content_type="application/xml")

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
