"""The base protocol to implement an operation.

All operations extend from an WFSMethod class.
This defines the parameters and output formats of the method.
This introspection data is also parsed by the GetCapabilities call.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Union

from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from django.http import HttpResponse
from django.template.loader import render_to_string

from gisserver.exceptions import InvalidParameterValue, MissingParameterValue
from gisserver.features import FeatureType

NoneType = type(None)

RE_SAFE_FILENAME = re.compile(r"\A[A-Za-z0-9]+[A-Za-z0-9.]*")  # no dot at the start.


@dataclass(frozen=True)
class Parameter:
    """The definition of an parameter for an WFS method.

    These parameters should be defined in the
    WFSMethod parameters attribute / get_parameters().

    These fields is used to parse the incoming request.
    The GetCapabilities method also reads the metadata of this value.
    """

    #: Name of the parameter (using the XML casing style)
    name: str

    #: Whether the parameter is required
    required: bool = False

    #: Optional parser callback to convert the parameter into a Python type
    parser: Callable[[str], Any] = None

    #: Whether to list this parameter in GetCapabilities
    in_capabilities: bool = False

    #: List of allowed values (also shown in GetCapabilities)
    allowed_values: Union[list, tuple, set, NoneType] = None

    #: Default value if it's not given
    default: Any = None

    #: Overridable dict for error messages
    error_messages: dict = field(default_factory=dict)

    def value_from_query(self, KVP: dict):  # noqa: C901
        """Parse a request variable using the type definition.

        This uses the dataclass settings to parse the incoming request value.
        """
        # URL-based key-value-pair parameters use uppercase.
        kvp_name = self.name.upper()
        value = KVP.get(kvp_name)

        # Check required field settings, both empty and missing value are treated the same.
        if not value:
            if self.required:
                raise MissingParameterValue(self.name, f"Empty {kvp_name} parameter")
            else:
                return self.default

        # Allow conversion into a python object
        if self.parser is not None:
            try:
                value = self.parser(value)
            except (TypeError, ValueError, NotImplementedError) as e:
                # TypeError/ValueError are raised by most handlers for unexpected data
                # The NotImplementedError can be raised by fes parsing.
                raise InvalidParameterValue(
                    self.name, f"Unable to parse {kvp_name} argument: {e}"
                ) from None

        # Validate against value choices
        self.validate_value(value)

        return value

    def validate_value(self, value):
        """Validate the parsed value.
        This method can be overwritten by a subclass if needed.
        """
        if self.allowed_values is not None and value not in self.allowed_values:
            msg = self.error_messages.get(
                "invalid", "Invalid value for {name}: {value}"
            )
            raise InvalidParameterValue(
                self.name, msg.format(name=self.name, value=value)
            )


class UnsupportedParameter(Parameter):
    def value_from_query(self, KVP: dict):
        kvp_name = self.name.upper()
        if kvp_name in KVP:
            raise InvalidParameterValue(
                self.name, f"Support for {self.name} is not implemented!"
            )
        return None


class OutputFormat:
    """Declare an output format for the method.

    These formats should be used in the ``output_formats`` section of the WFSMethod.
    """

    def __init__(
        self, content_type, renderer_class=None, **extra,
    ):
        self.content_type = content_type
        self.extra = extra
        self.subtype = self.extra.get("subtype")
        self.renderer_class = renderer_class

    def matches(self, value):
        """Test whether the 'value' is matched by this object."""
        return self.content_type == value or self.subtype == value

    def __str__(self):
        extra = "".join(f"; {name}={value}" for name, value in self.extra.items())
        return f"{self.content_type}{extra}"


class WFSMethod:
    """Basic interface to implement an WFS method.

    Each operation in this GIS-server extends from this base class. This class
    also exposes all requires metadata for the GetCapabilities request.
    """

    do_not_call_in_templates = True  # avoid __call__ execution in Django templates

    #: List the suported parameters for this method, extended by get_parameters()
    parameters: List[Parameter] = []

    #: List the supported output formats for this method.
    output_formats: List[OutputFormat] = []

    #: Default template to use for rendering
    xml_template_name = None

    #: Default content-type for render_xml()
    xml_content_type = "text/xml; charset=utf-8"

    def __init__(self, view):
        self.view = view  # an gisserver.views.GISView

    def get_parameters(self):
        """Dynamically return the supported parameters for this method."""
        parameters = [
            # Always add SERVICE and VERSION as required parameters
            # Part of BaseRequest:
            Parameter(
                "service",
                required=True,
                in_capabilities=True,
                allowed_values=list(self.view.accept_operations.keys()),
                error_messages={"invalid": "Unsupported service type: {value}."},
            ),
            Parameter(
                "version",
                required=True,  # Mandatory except for GetCapabilities
                allowed_values=self.view.accept_versions,
                error_messages={
                    "invalid": "WFS Server does not support VERSION {value}.",
                },
            ),
            # Common for all WFS methods:
            UnsupportedParameter("namespaces"),  # define output namespaces
        ] + self.parameters

        if self.output_formats:
            parameters += [
                # Part of StandardPresentationParameters:
                Parameter(
                    "outputFormat",
                    in_capabilities=True,
                    allowed_values=self.output_formats,
                    parser=self._parse_output_format,
                    default=self.output_formats[0],
                )
            ]

        return parameters

    def _parse_output_format(self, value) -> OutputFormat:
        """Select the proper OutputFormat object based on the input value"""
        try:
            return next(o for o in self.output_formats if o.matches(value))
        except StopIteration:
            raise InvalidParameterValue(
                "outputformat",
                f"'{value}' is not a permitted output format for this operation.",
            ) from None

    def parse_request(self, KVP: dict) -> Dict[str, Any]:
        """Parse the parameters of the request"""
        param_values = {
            param.name: param.value_from_query(KVP) for param in self.get_parameters()
        }

        # Update version if requested.
        # This is stored on the view, so exceptions also use it.
        if param_values.get("version"):
            self.view.set_version(param_values["version"])

        return param_values

    def __call__(self, **params):
        """Default call implementation: render an XML template."""
        context = self.get_context_data(**params)
        if "outputFormat" in params:
            output_format: OutputFormat = params["outputFormat"]

            if output_format.renderer_class is not None:
                # Streaming HTTP responses, e.g. GML32/GeoJSON output:
                renderer = output_format.renderer_class(self, **context)
                return renderer.get_response()

        return self.render_xml(context, **params)

    def get_context_data(self, **params):
        """Collect all arguments to use for rendering the XML template"""
        return {}

    def render_xml(self, context, **params):
        """Shortcut to render XML.

        This is the default method when the OutputFormat class doesn't have a renderer_class
        """
        return HttpResponse(
            render_to_string(
                self._get_xml_template_name(),
                context={
                    "view": self.view,
                    "app_xml_namespace": self.view.xml_namespace,
                    "server_url": self.view.server_url,
                    **context,
                },
            ),
            content_type=self.xml_content_type,
        )

    def _get_xml_template_name(self):
        """Generate the XML template name for this operation, and check it's file pattern"""
        service = self.view.KVP["SERVICE"].lower()
        template_name = (
            f"gisserver/{service}/{self.view.version}/{self.xml_template_name}"
        )

        # Since 'service' and 'version' are based on external input,
        # these values are double checked again to avoid remove file inclusion.
        if not RE_SAFE_FILENAME.match(service) or not RE_SAFE_FILENAME.match(
            self.view.version
        ):
            raise SuspiciousOperation(
                f"Refusing to render template name {template_name}"
            )

        return template_name


class WFSTypeNamesMethod(WFSMethod):
    """A base method that also resolved the TYPENAMES parameter."""

    def get_parameters(self):
        return super().get_parameters() + [
            # QGis sends both TYPENAME (wfs 1.x) and TYPENAMES (wfs 2.0) for DescribeFeatureType
            Parameter("typeNames", required=True, parser=self._parse_type_names)
        ]

    def _init_feature_types(self):
        """Initialize the 'self.feature_types'."""
        self.feature_types = self.view.get_feature_types()

        features_by_name = {ft.name: ft for ft in self.feature_types}
        if len(features_by_name) != len(self.feature_types):
            all_names = [ft.name for ft in self.feature_types]
            duplicates = ", ".join(
                sorted(set(n for n in all_names if all_names.count(n) > 1))
            )
            raise ImproperlyConfigured(
                f"FeatureType names should be unique: {duplicates}"
            )

        return features_by_name

    def _parse_type_names(self, type_names) -> List[FeatureType]:
        """Find the requested feature types by name"""
        features_by_name = self._init_feature_types()

        features = []
        for name in type_names.split(","):
            try:
                feature = features_by_name[name]
            except KeyError:
                raise InvalidParameterValue(
                    "typename",
                    f"Typename '{name}' doesn't exist in this server. "
                    f"Please check the capabilities and reformulate your request.",
                ) from None

            features.append(feature)
        return features
