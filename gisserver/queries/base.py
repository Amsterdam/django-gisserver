from django.db.models import QuerySet
from typing import Dict, List, Optional, Tuple

from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.output import FeatureCollection, SimpleFeatureCollection
from gisserver.parsers import fes20


class QueryExpression:
    """WFS base class for all queries.
    This object type is defined in the WFS spec.
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

    def resolve_type_name(self, type_name, locator="") -> FeatureType:
        """Find the feature type for a given name."""
        try:
            return self.all_feature_types[type_name]
        except KeyError:
            raise InvalidParameterValue(
                "typename",
                f"Typename '{type_name}' doesn't exist in this server. "
                f"Please check the capabilities and reformulate your request.",
            ) from None

    def get_hits(self) -> FeatureCollection:
        """Run the query, return the number of hits only."""
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
        """Run the query, return the full paginated results."""
        stop = start_index + count

        # The querysets are not executed until the very end.
        querysets = self.get_querysets()
        results = [
            SimpleFeatureCollection(feature_type, qs, start=start_index, stop=stop)
            for feature_type, qs in querysets
        ]

        number_matched = sum(collection.number_matched for collection in results)
        return FeatureCollection(results=results, number_matched=number_matched)

    def get_type_names(self) -> List[FeatureType]:
        """Tell which type names this query applies to."""
        raise NotImplementedError()

    def get_querysets(self) -> List[Tuple[FeatureType, QuerySet]]:
        """Construct the querysets that return the database results"""
        results = []
        for feature_type in self.get_type_names():
            queryset = self.get_queryset(feature_type)
            results.append((feature_type, queryset))

        return results

    def get_queryset(self, feature_type: FeatureType) -> QuerySet:
        """Generate the queryset for the specific feature type."""
        queryset = feature_type.get_queryset()

        # Apply filters
        fes_query = self.get_fes_query(feature_type)

        if self.value_reference is not None:
            # TODO: for now only check direct field names, no xpath (while query support it)
            if self.value_reference.element_name not in feature_type.fields:
                raise InvalidParameterValue(
                    "valueReference",
                    f"Field '{self.value_reference.xpath}' does not exist.",
                )

            # For GetPropertyValue, adjust the query so only that value is requested.
            field = fes_query.add_value_reference(self.value_reference)
            queryset = fes_query.filter_queryset(queryset, feature_type=feature_type)
            return queryset.values("pk", member=field)
        else:
            return fes_query.filter_queryset(queryset, feature_type=feature_type)

    def get_fes_query(self, feature_type: FeatureType):
        raise NotImplementedError()
