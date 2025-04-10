"""Generic Open Web Services (OWS) protocol bits to handle incoming requests.

This is the common logic between WFS, WMS and other protocols.

These translate both request-syntax formats in the same internal objects
that the rest of the controller/view logic can use.
"""

from .kvp import KVPRequest
from .requests import (
    BaseOwsRequest,
    parse_get_request,
    parse_post_request,
    resolve_kvp_parser_class,
    resolve_xml_parser_class,
)

__all__ = (
    "KVPRequest",
    "BaseOwsRequest",
    "resolve_kvp_parser_class",
    "resolve_xml_parser_class",
    "parse_get_request",
    "parse_post_request",
)
