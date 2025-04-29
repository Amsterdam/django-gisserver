"""Request parsing for the common Generic Open Web Services (OWS) protocol bits."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from django.http import QueryDict

from gisserver.exceptions import (
    ExternalParsingError,
    InvalidParameterValue,
    OperationNotSupported,
    OperationParsingFailed,
)
from gisserver.parsers.ast import AstNode, tag_registry
from gisserver.parsers.xml import NSElement, parse_xml_from_string, split_ns, xmlns

from .kvp import KVPRequest

__all__ = (
    "BaseOwsRequest",
    "resolve_kvp_parser_class",
    "resolve_xml_parser_class",
    "parse_get_request",
    "parse_post_request",
)


@dataclass
class BaseOwsRequest(AstNode):
    """Base request data for all request types of the OWS standards.
    This mirrors the ``<wfs:BaseRequestType>`` element from the WFS spec.
    """

    # dataclass limitation: when defaults are added, subclasses can't have required parameters anymore.
    service: str
    version: str | None  # none for GetCapabilities only
    handle: str | None

    @classmethod
    def from_xml(cls, element: NSElement):
        """Initialize from an XML POST request."""
        return cls(**cls.base_xml_init_parameters(element))

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Initialize from an KVP GET request."""
        return cls(**cls.base_kvp_init_parameters(kvp))

    @classmethod
    def base_xml_init_parameters(cls, element: NSElement) -> dict:
        """Parse the base attributes.
        This parses the syntax such as::

            <wfs:BaseRequest service="WFS" version="2.0.0" handle="...">

        """
        return dict(
            service=element.get_str_attribute("service"),
            version=element.get_str_attribute("version"),
            handle=element.attrib.get("handle"),
        )

    @classmethod
    def base_kvp_init_parameters(cls, kvp: KVPRequest) -> dict:
        """Parse the common Key-Value-Pair format (GET request parameters).
        This parses the syntax::

            ?SERVICE=WFS&VERSION=2.0.0
        """
        return dict(
            service=kvp.get_str("SERVICE"),
            version=kvp.get_str("VERSION"),
            handle=None,
        )

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        return {
            "SERVICE": self.service,
            "VERSION": str(self.version),
            "REQUEST": split_ns(self.xml_name)[1],
        }


@lru_cache
def _get_kvp_parsers() -> dict[str, dict[str, type[BaseOwsRequest]]]:
    """Find which classes are registered."""
    # This late initialization keeps the ability open in the future
    # to handle request types that are registered in third party code.
    ows_parsers = {}

    for xml_name, parser_class in tag_registry.find_subclasses(BaseOwsRequest).items():
        namespace, local_name = split_ns(xml_name)
        ows_parsers.setdefault(namespace, {})[local_name.upper()] = parser_class

    return ows_parsers


def resolve_kvp_parser_class(kvp: KVPRequest) -> type[BaseOwsRequest]:
    """Find the appropriate class to parse the KVP GET request data."""
    service = kvp.get_str("service").upper()
    request = kvp.get_str("request")

    # Find the appropriate request object
    service_types = _get_kvp_parsers()
    try:
        # Translating the GET parameter to a namespace makes connecting to the parser registration.
        # This doesn't take the VERSION/ACCEPTVERSIONS into account yet.
        namespace = xmlns[service.lower()].value
        request_classes = service_types[namespace]
    except KeyError:
        raise InvalidParameterValue(
            f"Unsupported service type: {service}.", locator="service"
        ) from None

    try:
        request_cls = request_classes[request.upper()]
    except KeyError:
        allowed = ", ".join(
            xml_tag for node in request_classes.values() for xml_tag in node.get_tag_names()
        )
        raise OperationNotSupported(
            f"'{request}' is not implemented, supported are: {allowed}.",
            locator="request",
        ) from None

    return request_cls


def resolve_xml_parser_class(root: NSElement) -> type[BaseOwsRequest]:
    """Find the correct class to parse the XML POST data with."""
    return tag_registry.resolve_class(root, allowed_types=(BaseOwsRequest,))


def parse_get_request(
    query_string: str | dict[str, str], ns_aliases: dict | None = None
) -> BaseOwsRequest:
    """Parse the WFS KVP GET request format into the internal request objects.
    Most code calls the resolver internally, but this variation is easier for unit testing.
    """
    if isinstance(query_string, str):
        query_string = QueryDict(query_string.lstrip("?"))

    kvp = KVPRequest(query_string, ns_aliases=ns_aliases)
    request_cls = resolve_kvp_parser_class(kvp)
    return request_cls.from_kvp_request(kvp)


def parse_post_request(xml_string: str | bytes, ns_aliases: dict | None = None) -> BaseOwsRequest:
    """Parse the XML POST request format into the internal request objects.
    Most code calls the resolver internally, but this variation is easier for unit testing.
    """
    try:
        root = parse_xml_from_string(xml_string, extra_ns_aliases=ns_aliases)
    except ExternalParsingError as e:
        raise OperationParsingFailed(f"Unable to parse XML: {e}") from e

    return tag_registry.node_from_xml(root, allowed_types=(BaseOwsRequest,))
