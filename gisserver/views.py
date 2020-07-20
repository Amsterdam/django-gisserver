"""The view layer parses the request, and dispatches it to an operation."""
import re
from typing import List, Optional, Type

from django.core.exceptions import (
    ImproperlyConfigured,
    PermissionDenied as Django_PermissionDenied,
    SuspiciousOperation,
)
from django.http import HttpResponse
from django.views import View

from gisserver import conf
from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OWSException,
    OperationNotSupported,
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

    #: Supported versions
    accept_versions = ("2.0.0",)

    #: Internal configuration of all available RPC calls.
    accept_operations = {}

    #: Metadata of the service:
    service_description: Optional[ServiceDescription] = None

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
        wfs_method_cls = self.get_operation_class()
        return self.call_operation(wfs_method_cls)

    def get_operation_class(self) -> Type[base.WFSMethod]:
        """Resolve the method that the client wants to call."""
        if not self.accept_operations:
            raise ImproperlyConfigured("View has no operations")

        # The service is always WFS
        service = self._get_required_arg("SERVICE").upper()
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

    def call_operation(self, wfs_method_cls: Type[base.WFSMethod]):
        """Call the resolved method."""
        wfs_method = wfs_method_cls(self)
        param_values = wfs_method.parse_request(self.KVP)
        return wfs_method(**param_values)  # goes into __call__()

    def _get_required_arg(self, argname):
        try:
            return self.KVP[argname]
        except KeyError:
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
    feature_types: List[FeatureType] = []

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

    def get_feature_types(self) -> List[FeatureType]:
        """Return all available feature types this server exposes"""
        return self.feature_types
