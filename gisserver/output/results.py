"""Wrappers for the results of GetFeature/GetPropertyValue"""
import math
import operator
from dataclasses import dataclass
from functools import reduce
from typing import List, Optional, Iterable

from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now, utc

from gisserver.features import FeatureType
from gisserver.types import BoundingBox


class SimpleFeatureCollection:
    """Wrapper to read a result set."""

    def __init__(
        self,
        feature_type: FeatureType,
        queryset: models.QuerySet,
        start: int,
        stop: int,
    ):
        self.feature_type = feature_type
        self.queryset = queryset
        self.start = start
        self.stop = stop
        self._result_cache = None

    def __iter__(self) -> Iterable[models.Model]:
        if self._result_cache is not None:
            return iter(self._result_cache)
        else:
            return self.queryset[self.start : self.stop].iterator()

    def fetch_results(self):
        """Forcefully read the results early."""
        if self._result_cache is None:
            self._result_cache = list(self)
        return len(self._result_cache)

    @cached_property
    def number_returned(self) -> int:
        """Return the number of results for this page."""
        # Count by fetching all data. Otherwise the results are queried twice.
        # For GML/XML, it's not possible the stream the queryset results
        # as the first tag needs to describe the number of results.
        self.fetch_results()
        return len(self._result_cache)

    @cached_property
    def number_matched(self) -> int:
        """Return the total number of matches across all pages."""
        return self.queryset.count()

    def get_bounding_box(self) -> BoundingBox:
        """Determine bounding box of all items."""
        self.fetch_results()  # Avoid querying results twice

        # Start with an obviously invalid bbox,
        # which corrects at the first extend_to_geometry call.
        bbox = BoundingBox(math.inf, math.inf, -math.inf, -math.inf)
        for instance in self:
            geomery_value = getattr(instance, self.feature_type.geometry_field_name)
            if geomery_value is None:
                continue

            bbox.extend_to_geometry(geomery_value)

        return bbox


@dataclass
class FeatureCollection:
    """Main result type for GetFeature."""

    #: All retrieved feature collections (one per FeatureType)
    results: List[SimpleFeatureCollection]

    #: Total number of features across all pages
    number_matched: Optional[int] = None

    #: URL of the next page
    next: Optional[str] = None

    #: URL of the previous page
    previous: Optional[str] = None

    def __post_init__(self):
        self.timestamp = now().astimezone(utc).isoformat()

    def get_bounding_box(self) -> BoundingBox:
        """Determine bounding box of all items."""
        # Combine the bounding box of all collections
        return reduce(operator.add, [c.get_bounding_box() for c in self.results])

    @cached_property
    def number_returned(self) -> int:
        """Return the total number of returned features"""
        return sum(c.number_returned for c in self.results)
