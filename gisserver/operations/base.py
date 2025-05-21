"""The base protocol to implement an operation.

The request itself is parsed by :mod:`gisserver.parsers.wfs20`, and handled here.
It can be seen as the "controller" that handles the actual request type.

All operations extend from an WFSOperation class.
This defines the metadata for the ``GetCapabilities`` call and possible output formats.

Each :class:`WFSOperation` can define a :attr:`~WFSOperation.parser_class`, or let it autodetect.
"""

from __future__ import annotations

import logging
import math
import re
import typing
from dataclasses import dataclass
from functools import cached_property

from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.template.loader import render_to_string

from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.output.base import OutputRenderer
from gisserver.parsers import ows
from gisserver.parsers.values import fix_type_name

if typing.TYPE_CHECKING:
    from gisserver.views import WFSView

logger = logging.getLogger(__name__)
NoneType = type(None)
R = typing.TypeVar("R", bound=OutputRenderer)

RE_SAFE_FILENAME = re.compile(r"\A[A-Za-z0-9]+[A-Za-z0-9.]*")  # no dot at the start.

__all__ = (
    "Parameter",
    "OutputFormat",
    "WFSOperation",
    "OutputFormatMixin",
    "XmlTemplateMixin",
)


@dataclass(frozen=True)
class Parameter:
    """The ``<ows:Parameter>`` tag to output in ``GetCapabilities``."""

    #: The name of the parameter
    name: str
    #: The values to report in ``<ows:AllowedValues><ows:Value>``.
    allowed_values: list[str]


class OutputFormat(typing.Generic[R]):
    """Declare an output format for the method.

    These formats are used in the :meth:`get_output_formats` for
    any :class:`WFSOperation` that implements :class:`OutputFormatMixin`.
    This also connects the output format with a :attr:`renderer_class`.
    """

    #: The class that performs the output rendering.
    renderer_class: type[R] | None = None

    def __init__(
        self,
        content_type,
        *,
        subtype=None,
        renderer_class: type[R] | None = None,  # None is special case for GetCapabilities
        max_page_size=None,
        title=None,
        in_capabilities=True,
        **extra,
    ):
        """
        :param content_type: The MIME-type used in the request to select this type.
        :param subtype: Shorter alias for the MIME-type.
        :param renderer_class: The class that performs the output rendering.
        :param max_page_size: Used to override the ``max_page_size`` of the renderer_class.
        :param title: A human-friendly name for an HTML overview page.
        :param in_capabilities: Whether this format needs to be advertised in GetCapabilities.
        :param extra: Any additional key-value pairs for the definition.
        """
        self.content_type = content_type
        self.subtype = subtype
        self.extra = extra
        self.renderer_class = renderer_class
        self.title = title
        self.in_capabilities = in_capabilities
        self._max_page_size = max_page_size

    def matches(self, value):
        """Test whether the 'value' is matched by this object."""
        if self.content_type == "application/gml+xml":
            # Allow "application/gml+xml; version=3.2" as sent by FME.
            # TODO rewrite this matching code in a clean way.
            value = value.split("; ", 1)[0]
        return self.content_type == value or self.subtype == value

    @property
    def identifier(self):
        """The identifier to use in templates as OUTPUTFORMAT input value."""
        return self.subtype or self.content_type

    @property
    def max_page_size(self):
        """Override the default max page size"""
        if self._max_page_size:
            return self._max_page_size
        elif self.renderer_class is not None:
            return self.renderer_class.max_page_size
        else:
            return None

    @property
    def has_infinite_page_size(self):
        """Return whether the output format can be unpaginated."""
        return self.max_page_size == math.inf

    def __str__(self):
        extra = "".join(f"; {name}={value}" for name, value in self.extra.items())
        if self.subtype:
            extra = f"; subtype={self.subtype}{extra}"
        return f"{self.content_type}{extra}"

    def __repr__(self):
        return f"<OutputFormat: {self}>"


class WFSOperation:
    """Basic interface to implement an WFS method.

    Each operation in this GIS-server extends from this base class. This class
    also exposes all requires metadata for the GetCapabilities request.
    """

    #: Optionally, mention explicitly what the parser class should be used.
    #: Otherwise, it's automatically resolved from the registered types.
    parser_class: type[ows.BaseOwsRequest] = None

    def __init__(self, view: WFSView, ows_request: ows.BaseOwsRequest):
        self.view = view
        self.ows_request = ows_request

    def get_parameters(self) -> list[Parameter]:
        """Parameters to advertise in the capabilities for this method."""
        return [
            # Always advertise SERVICE and VERSION as required parameters:
            Parameter("service", allowed_values=list(self.view.accept_operations.keys())),
            Parameter("version", allowed_values=self.view.accept_versions),
        ]

    def validate_request(self, ows_request: ows.BaseOwsRequest):
        """Validate the request."""

    def process_request(self, ows_request: ows.BaseOwsRequest):
        """Default call implementation: render an XML template."""
        raise NotImplementedError()

    @cached_property
    def all_feature_types_by_name(self) -> dict[str, FeatureType]:
        """Create a lookup for feature types by name.
        This can be cached as the :class:`WFSOperation` is instantiated with each request.
        """
        return {ft.xml_name: ft for ft in self.view.get_bound_feature_types()}

    def resolve_feature_type(self, type_name: str, locator: str = "typeNames") -> FeatureType:
        """Find the FeatureType defined in the application that corresponds with the XML type name."""
        alt_type_name = fix_type_name(type_name, self.view.xml_namespace)
        try:
            return self.all_feature_types_by_name[alt_type_name]
        except KeyError:
            if alt_type_name:
                logger.debug(
                    "Unable to locate '%s' (nor %s) in the server, options are: %r",
                    type_name,
                    alt_type_name,
                    list(self.all_feature_types_by_name),
                )
            else:
                logger.debug(
                    "Unable to locate '%s' in the server, options are: %r",
                    type_name,
                    list(self.all_feature_types_by_name),
                )
            raise InvalidParameterValue(
                f"Typename '{type_name}' doesn't exist in this server.",
                locator=locator or "typeNames",
            ) from None


class XmlTemplateMixin:
    """Mixin to support methods that render using a template."""

    #: Default template to use for rendering
    #: This is resolved as :samp:`gisserver/{service}/{version}/{xml_template_name}`.
    xml_template_name = None

    #: The content-type to render.
    xml_content_type = "text/xml; charset=utf-8"

    def process_request(self, ows_request: ows.BaseOwsRequest):
        """Process the request by rendering a Django template."""
        context = self.get_context_data()
        return self.render_xml(context, ows_request)

    def get_context_data(self):
        """Collect all arguments to use for rendering the XML template"""
        return {}

    def render_xml(self, context, ows_request: ows.BaseOwsRequest):
        """Render the response using a template."""
        return HttpResponse(
            render_to_string(
                self._get_xml_template_name(ows_request),
                context={
                    "view": self.view,
                    "app_xml_namespace": self.view.xml_namespace,
                    "server_url": self.view.server_url,
                    **context,
                },
            ),
            content_type=self.xml_content_type,
        )

    def _get_xml_template_name(self, ows_request: ows.BaseOwsRequest) -> str:
        """Generate the XML template name for this operation, and check its file pattern"""
        service = ows_request.service.lower()
        template_name = f"gisserver/{service}/{self.view.version}/{self.xml_template_name}"

        # Since 'service' and 'version' are based on external input,
        # these values are double-checked again to avoid remove file inclusion.
        if not RE_SAFE_FILENAME.match(service) or not RE_SAFE_FILENAME.match(self.view.version):
            raise SuspiciousOperation(f"Refusing to render template name {template_name}")

        return template_name


class OutputFormatMixin:
    """Mixin to support methods that handle different output formats."""

    def get_output_formats(self) -> list[OutputFormat]:
        """List all output formats. This is exposed in GetCapabilities,
        and used for internal rendering.
        """
        raise NotImplementedError()

    def resolve_output_format(self, value, locator="outputFormat") -> OutputFormat:
        """Select the proper OutputFormat object based on the input value"""
        # When using ?OUTPUTFORMAT=application/gml+xml", it is actually a URL-encoded space
        # character. Hence, spaces are replaced back to a '+' character to allow such notation
        # instead of forcing it to be ?OUTPUTFORMAT=application/gml%2bxml".
        for v in {value, value.replace(" ", "+")}:
            for o in self.get_output_formats():
                if o.matches(v):
                    return o
        raise InvalidParameterValue(
            f"'{value}' is not a permitted output format for this operation.",
            locator=locator or "outputFormat",
        ) from None
