"""The view layer parses the request, and dispatches it to an operation."""
from __future__ import annotations

import re
from urllib.parse import urlencode

from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied as Django_PermissionDenied
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from gisserver import conf
from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OperationNotSupported,
    OWSException,
    PermissionDenied,
)
from gisserver.features import FeatureType, ServiceDescription
from gisserver.operations import base, wfs20

SAFE_VERSION = re.compile(r"\A[0-9.]+\Z")


class GISView(View):
    """The base logic to implement OGC view like WFS.

    Each subclass defines 'accept_operations' with the desired RPC operations.
    """

    #: Define the namespace to use in the XML
    xml_namespace = "http://example.org/gisserver"

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

    #: Template to render a HTML welcome page for non-OGC requests.
    index_template_name = None

    #: Whether to render GET HTML pages
    use_html_templates = True

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
            exc = PermissionDenied("typeNames", text=str(exc) or None)
            return HttpResponse(
                exc.as_xml().encode("utf-8"),
                content_type="text/xml; charset=utf-8",
                status=exc.status_code,
                reason=exc.reason,
            )
        elif isinstance(exc, OWSException):
            # Wrap our XML-based exception into a response.
            exc.version = self.version  # Use negotiated version
            return HttpResponse(
                exc.as_xml().encode("utf-8"),
                content_type="text/xml; charset=utf-8",
                status=exc.status_code,
                reason=exc.reason,
            )

    def get(self, request, *args, **kwargs):
        """Entry point to handle HTTP GET requests.

        This parses the 'SERVICE' and 'REQUEST' parameters,
        to call the proper operation.

        All query parameters are handled as case-insensitive.
        """
        # Convert to WFS key-value-pair format.
        self.KVP = {key.upper(): value for key, value in request.GET.items()}

        # Perform early version parsing. The detailed validation happens by the operation
        # Parameter objects, but by performing an early check, templates can use that version.
        version = self.KVP.get("VERSION")
        if version and version in self.accept_versions:
            self.set_version(version)

        # Allow for an user-friendly opening page (hence the version check above)
        if self.use_html_templates and self.is_index_request():
            return self.render_index()

        # Normal WFS
        wfs_method_cls = self.get_operation_class()
        return self.call_operation(wfs_method_cls)

    def is_index_request(self):
        """Tell whether to index page should be shown."""
        # If none of the typical WFS parameters are given, and there aren't many other
        # (misspelled?) parameters on the query string, this is considered to be an index page.
        # Minimal request has 2 parameters (SERVICE=WFS&REQUEST=GetCapabilities).
        # Some servers also allow a default of SERVICE, thus needing even less.
        return len(self.KVP) < 2 and {
            "REQUEST",
            "SERVICE",
            "VERSION",
            "ACCEPTVERSIONS",
        }.isdisjoint(self.KVP.keys())

    def render_index(self):
        """Render the index page."""
        # Not using the whole TemplateResponseMixin config with configurable parameters.
        # If this really needs more configuration, overriding is likely just as easy.
        return render(
            self.request, self.get_index_template_names(), self.get_index_context_data()
        )

    def get_index_context_data(self, **kwargs):
        """Provide the context data for the index page."""
        service = self.KVP.get("SERVICE", self.default_service)
        root_url = self.request.build_absolute_uri()

        # Allow passing extra vendor parameters to the links generated in the template
        # (e.g. expand/embed logic)
        base_qs = {
            key: value
            for key, value in self.request.GET.items()
            if key.upper()
            not in ("SERVICE", "REQUEST", "VERSION", "OUTPUTFORMAT", "TYPENAMES")
        }
        base_query = urlencode(base_qs) + "&" if base_qs else ""

        return {
            "view": self,
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

    def get_index_template_names(self):
        """Get the index page template name.
        If no template is configured, some reasonable defaults are selected.
        """
        raw_service = self.KVP.get("SERVICE", self.default_service)
        if raw_service and raw_service in self.accept_operations:
            service = raw_service.lower()
        else:
            service = "default"

        if self.index_template_name:
            # Allow the same substitutions for a manually configured template.
            return [
                self.index_template_name.format(service=service, version=self.version)
            ]
        else:
            return [
                f"gisserver/{service}/{self.version}/index.html",
                f"gisserver/{service}/index.html",
                "gisserver/index.html",
            ]

    def get_operation_class(self) -> type[base.WFSMethod]:
        """Resolve the method that the client wants to call."""
        if not self.accept_operations:
            raise ImproperlyConfigured("View has no operations")

        # The service is always WFS
        service = self._get_required_arg("SERVICE", self.default_service).upper()
        try:
            operations = self.accept_operations[service]
        except KeyError:
            allowed = ", ".join(sorted(self.accept_operations.keys()))
            raise InvalidParameterValue(
                "service",
                f"'{service}' is an invalid service, supported are: {allowed}.",
            ) from None

        # Resolve the operation
        # In mapserver, the operation name is case insensitive.
        operation = self._get_required_arg("REQUEST").upper()
        uc_methods = {name.upper(): method for name, method in operations.items()}

        try:
            return uc_methods[operation]
        except KeyError:
            allowed = ", ".join(operations.keys())
            raise OperationNotSupported(
                "request",
                f"'{operation.lower()}' is not implemented, supported are: {allowed}.",
            ) from None

    def call_operation(self, wfs_method_cls: type[base.WFSMethod]):
        """Call the resolved method."""
        wfs_method = wfs_method_cls(self)
        param_values = wfs_method.parse_request(self.KVP)
        return wfs_method(**param_values)  # goes into __call__()

    def _get_required_arg(self, argname, default=None):
        try:
            return self.KVP[argname]
        except KeyError:
            if default is not None:
                return default
            raise MissingParameterValue(argname.lower()) from None

    def get_service_description(self, service: str) -> ServiceDescription:
        """Provide the (dynamically generated) service description."""
        return self.service_description or ServiceDescription(title="Unnamed")

    def set_version(self, version):
        """Enforce a particular version based on the request."""
        if not SAFE_VERSION.match(version):
            # Make really sure we didn't mess things up, as this causes file includes.
            raise SuspiciousOperation("Invalid/insecure version number parsed")

        # Enforce the requested version
        self.version = version

    @property
    def server_url(self):
        """Expose the server URLs for all operations to read."""
        return self.request.build_absolute_uri(self.request.path)


class WFSView(GISView):
    """A view for a single WFS server.

    This view exposes multiple dataset,
    each containing a single Django model (mapped to feature types in WFS).

    This class can be used by subclassing it, and redefining ``feature_types``
    or ``get_feature_types()``.
    """

    #: Maximum number of features to return
    max_page_size = conf.GISSERVER_DEFAULT_MAX_PAGE_SIZE

    #: Define the features (=tables) in this dataset.
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
        "XMLEncoding": False,  # HTTP POST requests
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
        """Return all available feature types this server exposes"""
        return self.feature_types

    def get_index_context_data(self, **kwargs):
        """Add WFS specific metadata"""
        wfs_output_formats = self.accept_operations["WFS"]["GetFeature"].output_formats

        context = super().get_index_context_data(**kwargs)
        context.update(
            {
                "wfs_features": self.get_feature_types(),
                "wfs_output_formats": wfs_output_formats,
                "wfs_filter_capabilities": self.wfs_filter_capabilities,
                "wfs_service_constraints": self.wfs_service_constraints,
            }
        )
        return context
