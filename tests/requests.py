from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Union

import pytest


class Url(Enum):
    NORMAL = "/v1/wfs/"
    FLAT = "/v1/wfs-flattened/"
    COMPLEX = "/v1/wfs-complextypes/"
    GENERATED = "/v1/wfs-gen-field/"


@dataclass
class Request:
    method: str
    _url: Url
    id: Optional[str]
    expect: Optional[Any]

    def __init__(self, *, id=None, expect=None, url: Url = Url.NORMAL):
        self.id = id
        self.expect = expect
        self._url = url

    def test_id(self):
        if self.id:
            return f"{self.method}-{self.id} ({self._url.name})"
        return f"{self.method} ({self._url.name})"

    @property
    def url(self):
        return self._url.value

    @url.setter
    def url(self, url: Url):
        self._url = url


@dataclass
class Get(Request):
    method = "GET"
    query: Union[str, Callable]

    def __init__(self, query, **kwargs):
        super().__init__(**kwargs)
        self.query = query


@dataclass
class Post(Request):
    method = "POST"
    body: Union[str, Callable]

    def __init__(self, body, **kwargs):
        super().__init__(**kwargs)
        self.body = body


# Decorator
def parametrize_response(*param_values: Request, url: Optional[Url] = None):
    """This is a decorator that wraps the parametrizing of "response", and allows us to
    set global flags (used for getting the correct url).

    Usage:
    ```
    @parametrize_response(
        Get("?query=test"),
        Get(lambda id: f"?query=test{id}", url=Url.COMPLEX),
        Post("<xml></xml>"),
        Post("<xml></xml>", expect=AssertionError),
        url=Url.FLAT,
    )
    def test_function(response):
        ...
    ```

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
        if url and request.url == Url.NORMAL.value:
            request.url = url

    def decorator(func):
        return pytest.mark.parametrize("response", param_values, indirect=True)(func)

    return decorator
