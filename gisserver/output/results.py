"""Wrappers for the results of GetFeature/GetPropertyValue.

The "SimpleFeatureCollection" and "FeatureCollection" and their
properties match the WFS 2.0 spec closely.
"""
import django
import math
import operator
from functools import reduce
from typing import List, Optional, Iterable

from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now, utc

from gisserver.features import FeatureType
from gisserver.geometries import BoundingBox


class SimpleFeatureCollection:
    """Wrapper to read a result set.

    This object type is defined in the WFS spec.
    It holds a collection of "wfs:member" objects.
    """

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
        self._used_iterator = False

    def __iter__(self) -> Iterable[models.Model]:
        if self._result_cache is not None:
            return iter(self._result_cache)
        elif self.start == self.stop == 0:
            # resulttype=hits
            return iter([])
        else:
            # This still allows prefetch_related() to work,
            # since QuerySet.iterator() is avoided.
            return iter(self.queryset[self.start : self.stop])

    def iterator(self):
        """Explicitly request the results to be streamed.

        This can be used by output formats that stream may results, and don't
        access `number_returned`. Note this is not compatible with prefetch_related().
        """
        self._used_iterator = True
        if self._result_cache is not None:
            # In case the results were read already, reuse that.
            return iter(self._result_cache)
        elif self.start == self.stop == 0:
            # resulttype=hits
            return iter([])
        else:
            if self.stop == math.inf:
                # Infinite page requested
                if self.start:
                    return self.queryset[self.start :].iterator()
                else:
                    return self.queryset.iterator()
            else:
                return self.queryset[self.start : self.stop].iterator()

    def first(self):
        try:
            # Don't query a full page, return only one instance (for GetFeatureById)
            # This also preserves the extra added annotations (like _as_gml_FIELD)
            return self.queryset[self.start]
        except IndexError:
            return None

    def fetch_results(self):
        """Forcefully read the results early."""
        if self._used_iterator:
            raise RuntimeError(
                "Results for feature collection are read twice. "
                "Avoid using SimpleFeatureCollection.iterator()."
            )

        if self._result_cache is None:
            self._result_cache = list(self)
        return len(self._result_cache)

    @cached_property
    def number_returned(self) -> int:
        """Return the number of results for this page."""
        if self.start == self.stop == 0:
            return 0  # resulttype=hits
        else:
            # Count by fetching all data. Otherwise the results are queried twice.
            # For GML/XML, it's not possible the stream the queryset results
            # as the first tag needs to describe the number of results.
            self.fetch_results()
            return len(self._result_cache)

    @cached_property
    def number_matched(self) -> int:
        """Return the total number of matches across all pages."""
        page_size = self.stop - self.start
        if page_size and self.number_returned < page_size:
            # For resulttype=results, an expensive COUNT query can be avoided
            # when this is the first and only page or the last page.
            return self.start + self.number_returned

        qs = self.queryset
        clean_annotations = {
            # HACK: remove database optimizations from output renderer.
            # Otherwise it becomes SELECT COUNT(*) FROM (SELECT AsGML(..), ...)
            key: value
            for key, value in qs.query.annotations.items()
            if not key.startswith("_as_")
        }
        if clean_annotations != qs.query.annotations:
            qs = self.queryset.all()  # make a clone to allow editing
            if django.VERSION >= (3, 0):
                qs.query.annotations = clean_annotations
            else:
                qs.query._annotations = clean_annotations

        return qs.count()

    def get_bounding_box(self) -> BoundingBox:
        """Determine bounding box of all items."""
        self.fetch_results()  # Avoid querying results twice

        # Start with an obviously invalid bbox,
        # which corrects at the first extend_to_geometry call.
        bbox = BoundingBox(math.inf, math.inf, -math.inf, -math.inf)
        geometry_field = self.feature_type.resolve_element(
            self.feature_type.geometry_field_name
        )
        for instance in self:
            geomery_value = geometry_field.get_value(instance)
            if geomery_value is None:
                continue

            bbox.extend_to_geometry(geomery_value)

        return bbox


CALCULATE = -9999999


class FeatureCollection:
    """WFS object that holds the result type for GetFeature.
    This object type is defined in the WFS spec.
    """

    def __init__(
        self,
        results: List[SimpleFeatureCollection],
        number_matched: Optional[int] = CALCULATE,
        next: Optional[str] = None,
        previous: Optional[str] = None,
    ):
        """
        :param results: All retrieved feature collections (one per FeatureType)
        :param number_matched: Total number of features across all pages
        :param next: URL of the next page
        :param previous: URL of the previous page
        """
        self.results = results
        self._number_matched = number_matched
        self.next = next
        self.previous = previous
        self.timestamp = now().astimezone(utc).isoformat()

    def get_bounding_box(self) -> BoundingBox:
        """Determine bounding box of all items."""
        # Combine the bounding box of all collections
        return reduce(operator.add, [c.get_bounding_box() for c in self.results])

    @cached_property
    def number_returned(self) -> int:
        """Return the total number of returned features"""
        return sum(c.number_returned for c in self.results)

    @cached_property
    def number_matched(self) -> Optional[int]:
        """The number of features matched, None means "unknown"."""
        if self._number_matched is None:
            return None  # WFS allows returning this as "unknown"
        elif self._number_matched == CALCULATE:
            # By making the number_matched lazy, the calling method has a chance to
            # decorate the results with extra annotations before they are evaluated.
            # This is needed since SimpleCollection.number_matched already evaluates the queryset.
            return sum(c.number_matched for c in self.results)
        else:
            # Evaluate any lazy attributes
            return int(self._number_matched)

    def __iter__(self):
        return iter(self.results)
