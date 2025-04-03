from __future__ import annotations

from django.db.models import QuerySet

from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.output import FeatureCollection, SimpleFeatureCollection
from gisserver.parsers import fes20
from gisserver.projection import FeatureProjection
from gisserver.types import split_xml_name


class QueryExpression:
    """WFS base class for all queries.
    This object type is defined in the WFS spec (as ``<fes:AbstractQueryExpression>``).

    The WFS server can initiate queries in multiple ways.
    This class provides the common interface for all these query types;
    whether the request provided "ad-hoc" parameters or called a stored procedure.
    Each query type has its own way of generating the actual database statement to perform.

    The subclasses can override the following logic:

    * :meth:`get_type_names` defines which types this query applies to.
    * :meth:`compile_query` defines how to filter the queryset.

    For full control, these methods can also be overwritten instead:

    * :meth:`get_queryset` defines the full results.
    * :meth:`get_hits` to return the collection for ``RESULTTYPE=hits``.
    * :meth:`get_results` to return the collection for ``RESULTTYPE=results``.
    """

    handle = ""
    value_reference: fes20.ValueReference | None = None
    property_names: list[fes20.ValueReference] | None = None
    projections: dict[FeatureType, FeatureProjection] | None = None

    def bind(
        self,
        all_feature_types: dict[str, FeatureType],
        value_reference: fes20.ValueReference | None = None,
        property_names: list[fes20.ValueReference] | None = None,
    ):
        """Bind the query to presentation-layer logic (e.g. request parameters).

        :param all_feature_types: Which features are queried.
        :param value_reference: Which field is returned (by ``GetPropertyValue``)
        :param property_name: Which field is returned (by ``GetFeature`` + propertyName parameter)
        """
        self.projections = {}
        self.all_feature_types = all_feature_types
        if value_reference is not None:
            self.value_reference = value_reference
        if property_names is not None:
            self.property_names = property_names

    def check_permissions(self, request):
        """Verify whether the user has access to view these data sources"""
        for feature_type in self.get_type_names():
            feature_type.check_permissions(request)

    def resolve_type_name(self, type_name, locator="typename") -> FeatureType:
        """Find the feature type for a given name.
        This is a utility that custom subclasses can use.
        """
        # Strip the namespace prefix. The Python ElementTree parser does
        # not expose the used namespace prefixes, so text-values can't be
        # mapped against it. As we expose just one namespace, just strip it.
        xmlns, type_name = split_xml_name(type_name)

        try:
            return self.all_feature_types[type_name]
        except KeyError:
            raise InvalidParameterValue(
                locator, f"Typename '{type_name}' doesn't exist in this server."
            ) from None

    def get_hits(self) -> FeatureCollection:
        """Run the query, return the number of hits only.

        Override this method in case you need full control over the response data.
        Otherwise, override :meth:`compile_query` or :meth:`get_queryset`.
        """
        results = []
        number_matched = 0
        for feature_type in self.get_type_names():
            queryset = self.get_queryset(feature_type)
            number_matched += queryset.count()

            # Include empty feature collections,
            # so the selected feature types are still known.
            results.append(
                SimpleFeatureCollection(
                    self, feature_type, queryset=queryset.none(), start=0, stop=0
                )
            )

        return FeatureCollection(results=results, number_matched=number_matched)

    def get_results(self, start_index=0, count=100) -> FeatureCollection:
        """Run the query, return the full paginated results.

        Override this method in case you need full control over the response data.
        Otherwise, override :meth:`compile_query` or :meth:`get_queryset`.
        """
        stop = start_index + count
        results = [
            # The querysets are not executed yet, until the output is reading them.
            SimpleFeatureCollection(
                self,
                feature_type,
                queryset=self.get_queryset(feature_type),
                start=start_index,
                stop=stop,
            )
            for feature_type in self.get_type_names()
        ]

        # number_matched is not given here, so some rendering formats can count it instead.
        # For GML it need to be printed at the start, but for GeoJSON it can be rendered
        # as the last bit of the response. That avoids performing an expensive COUNT query.
        return FeatureCollection(results=results)

    def get_queryset(self, feature_type: FeatureType) -> QuerySet:
        """Generate the queryset for the specific feature type.

        This method can be overwritten in subclasses to define the returned data.
        However, consider overwriting :meth:`compile_query` instead of simple data.
        """
        queryset = feature_type.get_queryset()

        # Apply filters
        compiler = self.compile_query(feature_type, using=queryset.db)

        # If defined, limit which fields will be queried.
        if self.property_names:
            for property_name in self.property_names:
                compiler.add_property_name(property_name)

        if self.value_reference is not None:
            if feature_type.resolve_element(self.value_reference.xpath) is None:
                raise InvalidParameterValue(
                    "valueReference",
                    f"Field '{self.value_reference.xpath}' does not exist.",
                )

            # For GetPropertyValue, adjust the query so only that value is requested.
            # This makes sure XPath attribute selectors are already handled by the
            # database query, instead of being a presentation-layer handling.
            field = compiler.add_value_reference(self.value_reference)
            queryset = compiler.filter_queryset(queryset, feature_type=feature_type)
            return queryset.values("pk", member=field)
        else:
            return compiler.filter_queryset(queryset, feature_type=feature_type)

    def get_type_names(self) -> list[FeatureType]:
        """Tell which type names this query applies to.

        This method needs to be defined in subclasses.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.get_type_names() should be implemented."
        )

    def get_projection(self, feature_type: FeatureType) -> FeatureProjection:
        """Provide the projection of this query for a given feature.

        NOTE: as the AdhocQuery has a typeNames (plural!) argument,
        this class still needs to check per feature type which fields to apply to.
        """
        try:
            return self.projections[feature_type]
        except KeyError:
            projection = FeatureProjection(feature_type, self.property_names)
            self.projections[feature_type] = projection
            return projection

    def compile_query(self, feature_type: FeatureType, using=None) -> fes20.CompiledQuery:
        """Define the compiled query that filters the queryset.

        Subclasses need to define this method, unless
        :meth:`get_queryset` is completely overwritten.
        """
        raise NotImplementedError()
