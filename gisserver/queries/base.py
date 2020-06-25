from django.db.models import QuerySet
from typing import Dict, List, Optional, Tuple

from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.output import FeatureCollection, SimpleFeatureCollection
from gisserver.parsers import fes20


class QueryExpression:
    """WFS base class for all queries.
    This object type is defined in the WFS spec.

    The subclasses can override the following logic:

    * :meth:`get_type_names` defines which types this query applies to.
    * :meth:`compile_query` defines how to filter the queryset.

    For full control, these methods can also be overwritten instead:

    * :meth:`get_queryset` defines the full results.
    * :meth:`get_hits` to return the collection for RESULTTYPE=hits.
    * :meth:`get_results` to return the collection for RESULTTYPE=results
    """

    handle = ""
    value_reference = None

    def bind(
        self,
        all_feature_types: Dict[str, FeatureType],
        value_reference: Optional[fes20.ValueReference],
    ):
        """Bind the query to presentation-layer logic"""
        self.all_feature_types = all_feature_types
        self.value_reference = value_reference

    def check_permissions(self, request):
        """Verify whether the user has access to view these data sources"""
        for feature_type in self.get_type_names():
            feature_type.check_permissions(request)

    def resolve_type_name(self, type_name, locator="") -> FeatureType:
        """Find the feature type for a given name.
        This is an utility that cusstom subclasses can use.
        """
        try:
            return self.all_feature_types[type_name]
        except KeyError:
            raise InvalidParameterValue(
                "typename",
                f"Typename '{type_name}' doesn't exist in this server. "
                f"Please check the capabilities and reformulate your request.",
            ) from None

    def get_hits(self) -> FeatureCollection:
        """Run the query, return the number of hits only.

        Override this method in case you need full control over the response data.
        Otherwise, override :meth:`compile_query` or :meth:`get_queryset`.
        """
        querysets = self.get_querysets()
        return FeatureCollection(
            results=[
                # Include empty feature collections,
                # so the selected feature types are still known.
                SimpleFeatureCollection(
                    feature_type=ft, queryset=qs.none(), start=0, stop=0
                )
                for ft, qs in querysets
            ],
            number_matched=sum([qs.count() for ft, qs in querysets]),
        )

    def get_results(self, start_index=0, count=100) -> FeatureCollection:
        """Run the query, return the full paginated results.

        Override this method in case you need full control over the response data.
        Otherwise, override :meth:`compile_query` or :meth:`get_queryset`.
        """
        stop = start_index + count

        # The querysets are not executed yet, until the output is reading them.
        querysets = self.get_querysets()
        return FeatureCollection(
            results=[
                SimpleFeatureCollection(feature_type, qs, start=start_index, stop=stop)
                for feature_type, qs in querysets
            ]
        )

    def get_querysets(self) -> List[Tuple[FeatureType, QuerySet]]:
        """Construct the querysets that return the database results."""
        results = []
        for feature_type in self.get_type_names():
            queryset = self.get_queryset(feature_type)
            results.append((feature_type, queryset))

        return results

    def get_queryset(self, feature_type: FeatureType) -> QuerySet:
        """Generate the queryset for the specific feature type.

        This method can be overwritten in subclasses to define the returned data.
        However, consider overwriting :meth:`compile_query` instead of simple data.
        """
        queryset = feature_type.get_queryset()

        # Apply filters
        compiler = self.compile_query(feature_type)

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

    def get_type_names(self) -> List[FeatureType]:
        """Tell which type names this query applies to.

        This method needs to be defined in subclasses.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.get_type_names() should be implemented."
        )

    def compile_query(self, feature_type: FeatureType) -> fes20.CompiledQuery:
        """Define the compiled query that filters the queryset.

        Subclasses need to define this method, unless
        :meth:`get_queryset` is completely overwritten.
        """
        raise NotImplementedError()
