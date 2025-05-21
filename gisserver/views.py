"""The view layer parses the request, and dispatches it to an operation."""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote_plus, urlencode

from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from django.core.exceptions import PermissionDenied as Django_PermissionDenied
from django.shortcuts import render
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from gisserver import conf
from gisserver.exceptions import (
    ExternalParsingError,
    InvalidParameterValue,
    OperationNotSupported,
    OperationParsingFailed,
    OperationProcessingFailed,
    OWSException,
    PermissionDenied,
    XmlElementNotSupported,
)
from gisserver.features import FeatureType, ServiceDescription
from gisserver.operations import base, wfs20
from gisserver.parsers.ows import (
    BaseOwsRequest,
    KVPRequest,
    resolve_kvp_parser_class,
    resolve_xml_parser_class,
)
from gisserver.parsers.xml import parse_xml_from_string, split_ns

logger = logging.getLogger(__name__)

SAFE_VERSION = re.compile(r"\A[0-9.]+\Z")


class OWSView(View):
    """The base logic to implement OGC view like WFS.

    Each subclass defines 'accept_operations' with the desired RPC operations.
    """

    #: Define the namespace to use in the XML
    xml_namespace = "http://example.org/gisserver"

    #: Define namespace aliases to use, default is ``{"app": self.xml_namespace}``.
    xml_namespace_aliases = None

    #: Default version to use
    version = "2.0.0"

    #: Allow to set a default service, so the SERVICE parameter can be omitted.
    default_service = None

    #: Supported versions
    accept_versions = ("2.0.0",)

    #: Internal configuration of all available RPC calls.
    accept_operations = {}

    #: Metadata of the service:
    service_description: ServiceDescription | None = None

    #: Template to render an HTML welcome page for non-OGC requests.
    index_template_name = None

    #: Whether to render GET HTML pages
    use_html_templates = True

    #: The OWS request, which contains the complete parsed request.
    ows_request: BaseOwsRequest = None

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        """Render proper XML errors for exceptions on all request types."""
        try:
            return super().dispatch(request, *args, **kwargs)
        except Exception as e:
            response = self.handle_exception(e)
            if response is not None:
                return response
            raise

    def handle_exception(self, exc):
        """Transform an exception into a OGC response.
        When nothing is returned, the exception is raised instead.
        """
        if isinstance(exc, Django_PermissionDenied):
            exc = PermissionDenied(str(exc) or None, locator="typeNames")
            return exc.as_response()
        elif isinstance(exc, OWSException):
            # Wrap our XML-based exception into a response.
            exc.version = self.version  # Use negotiated version
            return exc.as_response()
        else:
            return None

    @classmethod
    def get_xml_namespace_aliases(cls) -> dict[str, str]:
        """Provide all namespaces aliases with a namespace.
        This is most useful for parsing input.
        The default is: ``{"app": cls.xml_namespace}``.
        """
        return cls.xml_namespace_aliases or {"app": cls.xml_namespace}

    @classmethod
    def get_xml_namespaces_to_prefixes(cls) -> dict[str, str]:
        """Provide a mapping from namespace to prefix.
        This is most useful for rendering output.
        The default is: ``{cls.xml_namespace: "app"}``.
        """
        return {
            xml_namespace: prefix
            for prefix, xml_namespace in cls.get_xml_namespace_aliases().items()
        }

    def get(self, request, *args, **kwargs):
        """Entry point to handle HTTP GET requests.

        This parses the 'SERVICE' and 'REQUEST' parameters,
        to call the proper :class:`~gisserver.operations.base.WFSOperation`.

        All query parameters are handled as case-insensitive.
        """
        # Parse GET parameters in Key-Value-Pair syntax format.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Parsing GET parameters:\n%s",
                unquote_plus(
                    request.META["QUERY_STRING"].replace("\n&", "\n").replace("&", "\n")
                ).rstrip(),
            )
        self.kvp = kvp = KVPRequest(request.GET, ns_aliases=self.get_xml_namespace_aliases())

        # Get service (only raises error when value is missing and "default" parameter is not given)
        defaults = {"default": self.default_service} if self.default_service else {}
        service = kvp.get_str("service", **defaults).upper()

        # Perform early version parsing. The detailed validation happens by the operation
        # Parameter objects, but by performing an early check, templates can use that version.
        version = kvp.get_str("version", default=None)
        self.set_version(service, version)

        # Allow for a user-friendly opening page (hence the version check above)
        if self.use_html_templates and self.is_index_request():
            return self.render_index(service)

        # Find the registered operation that handles the request
        operation = kvp.get_str("request")
        wfs_operation_cls = self.get_operation_class(service, operation)

        # Parse the request syntax
        request_cls = wfs_operation_cls.parser_class or resolve_kvp_parser_class(kvp)
        self.ows_request = request_cls.from_kvp_request(kvp)

        # Process the request!
        return self.call_operation(wfs_operation_cls)

    def post(self, request, *args, **kwargs):
        """Entry point to handle HTTP POST requests.

        This parses the XML to get the correct service and operation,
        to call the proper :class:`~gisserver.operations.base.WFSOperation`.
        """
        # Parse the XML body
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Parsing POST:\n%s", request.body.decode().rstrip())
        try:
            root = parse_xml_from_string(
                request.body, extra_ns_aliases=self.get_xml_namespace_aliases()
            )
        except ExternalParsingError as e:
            raise OperationParsingFailed(f"Unable to parse XML: {e}") from e

        # Find the registered operation that handles the request
        service = (
            root.attrib.get("service", self.default_service)
            if self.default_service
            else root.get_str_attribute("service")
        )

        # Perform early version check. version can be omitted for GetCapabilities
        self.set_version(service, root.attrib.get("version"))

        # Find the registered operation that handles the request
        namespace, operation = split_ns(root.tag)
        wfs_operation_cls = self.get_operation_class(service, operation)

        try:
            # Parse the request syntax
            request_cls = wfs_operation_cls.parser_class or resolve_xml_parser_class(root)
            self.ows_request = request_cls.from_xml(root)

            # Process the request!
            return self.call_operation(wfs_operation_cls)
        except XmlElementNotSupported as e:
            # Unknown XML element, e.g. wrong namespace.
            raise OperationNotSupported(str(e), locator=root.attrib.get("handle")) from e
        except (OperationParsingFailed, OperationProcessingFailed) as e:
            # The WFS spec dictates that these exceptions
            # (and ResponseCacheExpired, CannotLockAllFeatures, FeaturesNotLocked which we don't raise)
            # should report the 'handle' in the 'locator' argument of the exception when it was provided.
            if self.ows_request.handle:
                e.locator = self.ows_request.handle
            raise

    def is_index_request(self):
        """Tell whether to index page should be shown."""
        # If none of the typical WFS parameters are given, and there aren't many other
        # (misspelled?) parameters on the query string, this is considered to be an index page.
        # Minimal request has 2 parameters (SERVICE=WFS&REQUEST=GetCapabilities).
        # Some servers also allow a default of SERVICE, thus needing even less.
        return (
            self.request.method == "GET"
            and len(self.request.GET) < 2
            and {
                "REQUEST",
                "SERVICE",
                "VERSION",
                "ACCEPTVERSIONS",
            }.isdisjoint(key.upper() for key in self.request.GET)
        )

    def render_index(self, service: str | None = None):
        """Render the index page."""
        # Not using the whole TemplateResponseMixin config with configurable parameters.
        # If this really needs more configuration, overriding is likely just as easy.
        return render(
            self.request,
            self.get_index_template_names(service),
            self.get_index_context_data(service=service),
        )

    def get_index_context_data(self, service: str | None = None, **kwargs):
        """Provide the context data for the index page."""
        root_url = self.request.build_absolute_uri()

        # Allow passing extra vendor parameters to the links generated in the template
        # (e.g. expand/embed logic)
        base_qs = {
            key: value
            for key, value in self.request.GET.items()
            if key.upper() not in ("SERVICE", "REQUEST", "VERSION", "OUTPUTFORMAT", "TYPENAMES")
        }
        base_query = urlencode(base_qs) + "&" if base_qs else ""

        return {
            "view": self,
            "xml_namespaces": self.get_xml_namespaces_to_prefixes(),
            "service": service,
            "root_url": root_url,
            "base_query": base_query,
            "connect_url": root_url,
            "version": self.version,
            "service_description": self.get_service_description(service),
            "accept_versions": self.accept_versions,
            "accept_operations": self.accept_operations,
            **kwargs,
        }

    def get_index_template_names(self, service: str | None = None):
        """Get the index page template name.
        If no template is configured, some reasonable defaults are selected.
        """
        service = service.lower() if service and service in self.accept_operations else "default"
        if self.index_template_name:
            # Allow the same substitutions for a manually configured template.
            return [self.index_template_name.format(service=service, version=self.version)]
        else:
            return [
                f"gisserver/{service}/{self.version}/index.html",
                f"gisserver/{service}/index.html",
                "gisserver/index.html",
            ]

    def get_operation_class(self, service: str, request: str) -> type[base.WFSOperation]:
        """Resolve the method that the client wants to call."""
        if not self.accept_operations:
            raise ImproperlyConfigured("View has no operations")

        try:
            operations = self.accept_operations[service.upper()]
        except KeyError:
            allowed = ", ".join(sorted(self.accept_operations.keys()))
            raise InvalidParameterValue(
                f"'{service}' is not supported, available are: {allowed}.",
                locator="service",
            ) from None

        # Resolve the operation
        # In mapserver, the operation name is case-insensitive.
        uc_methods = {name.upper(): method for name, method in operations.items()}
        try:
            return uc_methods[request.upper()]
        except KeyError:
            allowed = ", ".join(operations.keys())
            raise OperationNotSupported(
                f"'{request}' is not implemented, supported are: {allowed}.",
                locator="request",
            ) from None

    def call_operation(self, wfs_operation_cls: type[base.WFSOperation]):
        """Call the resolved method."""
        self.request.ows_request = self.ows_request  # for check_permissions()

        wfs_operation = wfs_operation_cls(self, self.ows_request)
        wfs_operation.validate_request(self.ows_request)
        return wfs_operation.process_request(self.ows_request)

    def get_service_description(self, service: str | None = None) -> ServiceDescription:
        """Provide the (dynamically generated) service description."""
        return self.service_description or ServiceDescription(title="Unnamed")

    def set_version(self, service: str, version: str | None):
        """Enforce a particular version based on the request."""
        if service.upper() not in self.accept_operations:
            allowed = ", ".join(sorted(self.accept_operations.keys()))
            raise InvalidParameterValue(
                f"'{service}' is not supported, available are: {allowed}.",
                locator="service",
            ) from None

        if not version:
            return

        if not SAFE_VERSION.match(version):
            # Make really sure we didn't mess things up, as this causes file includes.
            raise SuspiciousOperation("Invalid/insecure version number parsed")

        if version not in self.accept_versions:
            raise InvalidParameterValue(
                f"This server does not support {service} version {version}.", locator="version"
            )

        # Enforce the requested version
        self.version = version

    @property
    def server_url(self):
        """Expose the server URLs for all operations to read."""
        return self.request.build_absolute_uri(self.request.path)


class WFSView(OWSView):
    """A view for a single WFS server.

    This view exposes multiple dataset,
    each containing a single Django model (mapped to feature types in WFS).

    This class can be used by subclassing it, and redefining ``feature_types``
    or ``get_feature_types()``.
    """

    #: Maximum number of features to return
    max_page_size = conf.GISSERVER_DEFAULT_MAX_PAGE_SIZE

    #: Define the features (=tables) in this dataset.
    #: For dynamic per-request logic, consider overwriting :meth:`get_feature_types` instead.
    feature_types: list[FeatureType] = []

    #: Internal configuration of all available RPC calls.
    accept_operations = {
        "WFS": {
            "GetCapabilities": wfs20.GetCapabilities,
            "DescribeFeatureType": wfs20.DescribeFeatureType,
            "GetFeature": wfs20.GetFeature,
            "GetPropertyValue": wfs20.GetPropertyValue,
            "ListStoredQueries": wfs20.ListStoredQueries,
            "DescribeStoredQueries": wfs20.DescribeStoredQueries,
        }
    }

    #: Since URLs to this view are already specifically for WFS,
    #: allow to omit the service name.
    default_service = "WFS"

    #: Metadata of the capabilities:
    wfs_service_constraints = {
        "ImplementsBasicWFS": True,  # Advanced queries/xpath
        "ImplementsTransactionalWFS": False,  # only reads
        "ImplementsLockingWFS": False,  # only basic WFS
        "KVPEncoding": True,  # HTTP GET support
        "XMLEncoding": True,  # HTTP POST requests
        "SOAPEncoding": False,  # no SOAP requests
        "ImplementsInheritance": False,
        "ImplementsRemoteResolve": False,
        "ImplementsResultPaging": True,  # missing next/previous for START / COUNT
        "ImplementsStandardJoins": False,  # returns records as wfs:Tuple in GetFeature
        "ImplementsSpatialJoins": False,
        "ImplementsTemporalJoins": False,
        "ImplementsFeatureVersioning": False,
        "ManageStoredQueries": False,
        #
        # Mentioned as operation constraint in WFS spec:
        "PagingIsTransactionSafe": False,
    }

    #: Metadata of filtering capabilities
    wfs_filter_capabilities = {
        "ImplementsQuery": True,  # <fes:AbstractQueryElement> needed for WFS simple
        "ImplementsAdHocQuery": True,  # <fes:AbstractAdhocQueryElement> needed for WFS simple
        "ImplementsFunctions": True,  # <fes:Function> support
        "ImplementsResourceId": True,  # <fes:ResourceId> support
        "ImplementsMinStandardFilter": True,  # <fes:PropertyIs...> support
        "ImplementsStandardFilter": True,  # <fes:And>, <fes:Or> and advanced functions
        "ImplementsMinSpatialFilter": True,  # <fes:BBOX>
        "ImplementsSpatialFilter": True,  # Other spatial functions
        "ImplementsMinTemporalFilter": False,  # mapserver: true (During)
        "ImplementsTemporalFilter": False,
        "ImplementsVersionNav": False,  # <fes:ResourceId version="..">
        "ImplementsSorting": True,  # SORTBY parameter
        "ImplementsExtendedOperators": False,
        "ImplementsMinimumXPath": True,  # incomplete like mapserver, needed for cite
        "ImplementsSchemaElementFunc": False,
    }

    def get_feature_types(self) -> list[FeatureType]:
        """Return all available feature types this server exposes.

        This method may be overwritten to provide feature types dynamically,
        for example to give them different elements based on user permissions.
        """
        return self.feature_types

    def get_bound_feature_types(self) -> list[FeatureType]:
        """Internal logic wrapping the FeatureType definitions provided by the developer.
        This binds the XML namespace information from this view to the declared types.
        """
        feature_types = self.get_feature_types()
        for feature_type in feature_types:
            # Make sure the feature type can advertise itself with an XML namespace.
            feature_type.bind_namespace(default_xml_namespace=self.xml_namespace)
        return feature_types

    def get_index_context_data(self, **kwargs) -> dict:
        """Get the context data for the index template"""
        context = super().get_index_context_data(**kwargs)
        context.update(
            {
                "GISSERVER_SUPPORTED_CRS_ONLY": conf.GISSERVER_SUPPORTED_CRS_ONLY,
                "wfs_features": self.get_bound_feature_types(),
                "wfs_output_formats": self._get_wfs_output_formats(),
                "wfs_filter_capabilities": self.wfs_filter_capabilities,
                "wfs_service_constraints": self.wfs_service_constraints,
            }
        )
        return context

    def _get_wfs_output_formats(self) -> list[base.OutputFormat]:
        """Find the output formats of the ``GetFeature`` operation for the HTML index."""
        get_feature_operation = self.accept_operations["WFS"]["GetFeature"]
        operation = get_feature_operation(self, ows_request=None)

        # Get output formats, remove duplicates (e.g. GeoJSON/geojson alias)
        wfs_output_formats = []
        seen = set()
        for output_format in operation.get_output_formats():
            if output_format.identifier not in seen:
                wfs_output_formats.append(output_format)
            seen.add(output_format.identifier)
        return wfs_output_formats

    def get_xml_schema_url(self, feature_types: list[FeatureType]) -> str:
        """Return the XML schema URL for the given feature types.
        This is used in the GML output rendering.
        """
        app_namespaces = self.get_xml_namespaces_to_prefixes()
        type_names = ",".join(
            f"{app_namespaces[ft.xml_namespace]}:{ft.name}" for ft in feature_types
        )
        return (
            f"{self.server_url}?SERVICE=WFS&VERSION=2.0.0"
            f"&REQUEST=DescribeFeatureType&TYPENAMES={type_names}"
        )

    def check_permissions(self, feature_type: FeatureType):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.

        This can access: ``self.request`` (the Django HTTPRequest) and ``self.ows_request``.
        The latter contains a parsed request object
        from the :mod:`gisserver.parsers.wfs20` package,
        such as the parsed :class:`~gisserver.parsers.wfs20.GetFeature`
        or :class:`~gisserver.parsers.wfs20.GetPropertyValue` request.
        """
