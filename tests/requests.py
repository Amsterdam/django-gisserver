from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Union

import pytest


class URL_TYPE(Enum):
    NORMAL = "NORMAL"
    FLAT = "FLAT"
    COMPLEX = "COMPLEX"
    GENERATED = "GENERATED"


URLS = {
    URL_TYPE.NORMAL: "/v1/wfs/",
    URL_TYPE.FLAT: "/v1/wfs-flattened/",
    URL_TYPE.COMPLEX: "/v1/wfs-complextypes/",
    URL_TYPE.GENERATED: "/v1/wfs-gen-field/",
}


@dataclass
class Request:
    method: str
    url_type: URL_TYPE
    id: Optional[str]
    expect: Optional[Any]

    def __init__(self, *, id=None, expect=None, url_type=URL_TYPE.NORMAL):
        self.id = id
        self.expect = expect
        self.url_type = URL_TYPE(url_type)

    @property
    def url(self):
        return URLS[self.url_type]


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
def parametrize_response(param_values, *, url_type: URL_TYPE = URL_TYPE.NORMAL, setup=None):
    """This is a decorator that wraps the parametrizing of "response", and allows us to
    set global flags (used for getting the correct url).

    Usage:
    ```
    @parametrize_response(
        [
            Get("?query=test"),
            Get(lambda id: f"?query=test{id}"),
            Post("<xml></xml>"),
            Post("<xml></xml>", expect=AssertionError),
        ],
        url_type="FLAT",
    )
    def test_function(response):
        ...
    ```

    Note that each Request value can also take its own url_type, although you can also pass in
    a global url_type as in the above example.

    Requests (Get, Post) either get a string query/body argument or a Callable, which can be used
    later in the testing function to perform different requests at different times in the test.
    In this case, you need to call the response() to get an actual response object in your test.

    NB: When your response depends on other fixtures (for example because you need to have
    some rows in the database), ensure the `response` fixture argument comes at the end of the
    testing function arguments.
    """
    for request in param_values:
        if url_type and request.url_type == URL_TYPE.NORMAL:
            request.url_type = URL_TYPE(url_type)

    def decorator(func):
        return pytest.mark.parametrize("response", param_values, indirect=True)(func)

    return decorator
