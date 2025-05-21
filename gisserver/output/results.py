"""Wrappers for the results of GetFeature/GetPropertyValue.

The "SimpleFeatureCollection" and "FeatureCollection" and their
properties match the WFS 2.0 spec closely.
"""

from __future__ import annotations

import math
import typing
from collections.abc import Iterable
from datetime import timezone
from functools import cached_property

from django.db import models
from django.utils.timezone import now

from gisserver import conf
from gisserver.exceptions import wrap_filter_errors
from gisserver.features import FeatureType

from .iters import ChunkedQuerySetIterator, CountingIterator

if typing.TYPE_CHECKING:
    from gisserver.projection import FeatureProjection, QueryExpression


CALCULATE = -9999999


class SimpleFeatureCollection:
    """Wrapper to read a result set.

    This object type is defined in the WFS spec.
    It holds a collection of ``<wfs:member>`` objects.
    """

    def __init__(
        self,
        source_query: QueryExpression,
        feature_types: list[FeatureType],
        queryset: models.QuerySet,
        start: int,
        stop: int,
        number_matched: int | None = CALCULATE,
    ):
        self.source_query = source_query
        self.feature_types = feature_types
        self.queryset = queryset
        self.start = start
        self.stop = stop
        self._number_matched = number_matched

        self._result_cache = None
        self._result_iterator = None
        self._has_more = None

        # Tell that is a resultType=hits request.
        # Typically, start and stop are 0. However, for resultType=hits with count,
        # that does not apply. Instead, it detects whether the known amount is already provided.
        # Detecting that queryset.none() is provided won't work, as that can be used by IdOperator too.
        self._is_hits_request = number_matched is not None and number_matched != CALCULATE

    def __iter__(self) -> Iterable[models.Model]:
        """Iterate through all results.

        Depending on the output format (and whether pagination is read first),
        the results can either be cached first, or be streamed without caching.
        This picks the best-performance scenario in most cases.
        """
        if self._is_hits_request:
            self._result_cache = []

        if self._result_cache is not None:
            # Repeat what's cached if reading again.
            return iter(self._result_cache)
        elif self.queryset._prefetch_related_lookups:
            # Optimal solution to have an iterator that also handles prefetches
            return self._chunked_iterator()
        else:
            # No need to fetch everything first, can just stream the results.
            return self.iterator()

    def iterator(self):
        """Explicitly request the results to be streamed.

        This can be used by output formats that stream results, and don't
        access :attr:`number_returned`.
        Note this is not compatible with ``prefetch_related()``.
        """
        if self._result_iterator is not None:
            raise RuntimeError("Results for feature collection are read twice.")

        if self._result_cache is not None:
            # In case the results were read already, reuse that.
            return iter(self._result_cache)
        elif self._is_hits_request:
            # resulttype=hits
            return iter([])
        else:
            if self._use_sentinel_record:
                model_iter = self._paginated_queryset(add_sentinel=True).iterator()
                self._result_iterator = CountingIterator(
                    model_iter, max_results=(self.stop - self.start)
                )
            else:
                model_iter = self._paginated_queryset().iterator()
                self._result_iterator = CountingIterator(model_iter)
            return iter(self._result_iterator)

    def _chunked_iterator(self):
        """Generate an interator that processes results in chunks."""
        # Private function so the same logic of .iterator() is not repeated.
        self._result_iterator = ChunkedQuerySetIterator(self._paginated_queryset())
        return iter(self._result_iterator)

    def _paginated_queryset(self, add_sentinel=True) -> models.QuerySet:
        """Apply the pagination to the queryset."""
        if self.stop == math.inf:
            # Infinite page requested
            if self.start:
                return self.queryset[self.start :]
            else:
                return self.queryset
        else:
            return self.queryset[self.start : self.stop + (1 if add_sentinel else 0)]

    def first(self):
        with wrap_filter_errors(self.source_query):
            try:
                # Don't query a full page, return only one instance (for GetFeatureById)
                # This also preserves the extra added annotations (like _as_gml_FIELD)
                return self.queryset[self.start]
            except IndexError:
                return None

    def fetch_results(self):
        """Forcefully read the results early."""
        if self._result_cache is not None:
            return
        if self._result_iterator is not None:
            raise RuntimeError("Results for feature collection are read twice.")

        if self._is_hits_request:
            self._result_cache = []
        else:
            # This still allows prefetch_related() to work,
            # since QuerySet.iterator() is avoided.
            if self.stop == math.inf:
                # Infinite page requested, see if start is still requested
                qs = self.queryset[self.start :] if self.start else self.queryset.all()

                with wrap_filter_errors(self.source_query):
                    self._result_cache = list(qs)
            elif self._use_sentinel_record:
                # No counting, but instead fetch an extra item as sentinel to see if there are more results.
                qs = self.queryset[self.start : self.stop + 1]

                with wrap_filter_errors(self.source_query):
                    page_results = list(qs)

                # The stop + 1 sentinel allows checking if there is a next page.
                # This means no COUNT() is needed to detect that.
                page_size = self.stop - self.start
                self._has_more = len(page_results) > page_size
                if self._has_more:
                    # remove extra element
                    page_results.pop()

                self._result_cache = page_results
            else:
                # Fetch exactly the page size, no more is needed.
                # Will use a COUNT on the total table, so it can be used to see if there are more pages.
                qs = self.queryset[self.start : self.stop]

                with wrap_filter_errors(self.source_query):
                    self._result_cache = list(qs)

    @cached_property
    def _use_sentinel_record(self) -> bool:
        """Tell whether a sentinel record should be included in the result set.
        This is used to determine whether there are more results, without having to perform a COUNT query
        """
        return conf.GISSERVER_COUNT_NUMBER_MATCHED == 0 or (
            conf.GISSERVER_COUNT_NUMBER_MATCHED == 2 and self.start
        )

    @cached_property
    def number_returned(self) -> int:
        """Return the number of results for this page."""
        if self._is_hits_request:
            return 0
        elif self._result_iterator is not None:
            # When requesting the data after the fact, results are counted.
            return self._result_iterator.number_returned
        else:
            # Count by fetching all data. Otherwise, the results are queried twice.
            # For GML/XML, it's not possible the stream the queryset results
            # as the first tag needs to describe the number of results.
            self.fetch_results()
            return len(self._result_cache)

    @property
    def number_matched(self) -> int:
        """Return the total number of matches across all pages."""
        if self._is_hits_request:
            if self.stop:
                # resulttype=hits&COUNT=n should minimize how many are "matched".
                return min(self._number_matched, self.stop - self.start)
            else:
                return self._number_matched
        elif self._number_matched != CALCULATE:
            # Return previously cached result
            return self._number_matched

        if self._is_surely_last_page:
            # For resulttype=results, an expensive COUNT query can be avoided
            # when this is the first and only page or the last page.
            return self.start + self.number_returned

        qs = self.queryset
        clean_annotations = {
            # HACK: remove database optimizations from output renderer.
            # Otherwise, it becomes SELECT COUNT(*) FROM (SELECT AsGML(..), ...)
            key: value
            for key, value in qs.query.annotations.items()
            if not key.startswith("_as_") and not key.startswith("_As")  # AsGML / AsEWKT
        }
        if clean_annotations != qs.query.annotations:
            qs = self.queryset.all()  # make a clone to allow editing
            qs.query.annotations = clean_annotations

        # Calculate, cache and return
        with wrap_filter_errors(self.source_query):
            self._number_matched = qs.count()
        return self._number_matched

    @property
    def _is_surely_last_page(self):
        """Return true when it's totally clear this is the last page."""
        if self.start == self.stop == 0:
            return True  # hits request without count
        elif self._is_hits_request:
            return False

        # Optimization to avoid making COUNT() queries when we can already know the answer.
        if self.stop == math.inf:
            return True  # Infinite page requested
        elif self._use_sentinel_record:
            if self._has_more is not None:
                # did page+1 record check here, answer is known.
                return not self._has_more
            elif (
                isinstance(self._result_iterator, CountingIterator)
                and self._result_iterator.has_more is not None
            ):
                # did page+1 record check via the CountingIterator.
                return not self._result_iterator.has_more

        # Here different things will happen.
        # For GeoJSON output, the iterator was read first, and `number_returned` is already filled in.
        # For GML output, the pagination details are requested first, and will fetch all data.
        # Hence, reading `number_returned` here can be quite an intensive operation.
        page_size = self.stop - self.start
        return page_size and (self.number_returned < page_size or self._has_more is False)

    @property
    def has_next(self):
        if self.stop == math.inf or (self.start == self.stop == 0):
            return False
        elif self._has_more is not None:
            return self._has_more  # did page+1 record check, answer is known.
        elif self._is_surely_last_page:
            return False  # Fewer results than expected, answer is known.

        if self._is_hits_request:
            return self.stop <= self._number_matched
        else:
            # This will perform an slow COUNT() query...
            return self.stop < self.number_matched

    @cached_property
    def projection(self) -> FeatureProjection:
        """Provide the projection to render these results with."""
        # Note this attribute would technically be part of the 'query' object,
        # but since the projection needs to be calculated once, it's stored here for convenience.
        return self.source_query.get_projection()


class FeatureCollection:
    """WFS object that holds the result type for ``GetFeature``.
    This object type is defined in the WFS spec.
    It holds a collection of :class:`SimpleFeatureCollection` results.
    """

    def __init__(
        self,
        results: list[SimpleFeatureCollection],
        number_matched: int | None = CALCULATE,
        next: str | None = None,
        previous: str | None = None,
    ):
        """
        :param source_query: The query that generated this output.
        :param results: All retrieved feature collections (one per FeatureType)
        :param number_matched: Total number of features across all pages
        :param next: URL of the next page
        :param previous: URL of the previous page
        """
        self.results = results
        self._number_matched = number_matched
        self.next = next
        self.previous = previous
        self.date = now()
        self.timestamp = self.date.astimezone(timezone.utc).isoformat()

    @cached_property
    def number_returned(self) -> int:
        """Return the total number of returned features"""
        return sum(c.number_returned for c in self.results)

    @cached_property
    def number_matched(self) -> int | None:
        """The number of features matched, None means "unknown"."""
        if self._number_matched is None:
            return None  # WFS allows returning this as "unknown"
        elif self._number_matched == CALCULATE:
            # By making the number_matched lazy, the calling method has a chance to
            # decorate the results with extra annotations before they are evaluated.
            # This is needed since SimpleCollection.number_matched already evaluates the queryset.
            if conf.GISSERVER_COUNT_NUMBER_MATCHED == 0 or (
                conf.GISSERVER_COUNT_NUMBER_MATCHED == 2 and self.results[0].start > 0
            ):
                # Report "unknown" for either all pages, or the second page.
                # Most clients don't need this metadata, and thus we avoid a COUNT query.
                return None

            return sum(c.number_matched for c in self.results)
        else:
            # Evaluate any lazy attributes
            return int(self._number_matched)

    @property
    def has_next(self) -> bool:
        """Efficient way to see if a next link needs to be written.

        This method will show up in profiling through
        as it will be the first moment where queries are executed.
        """
        if all(c._is_surely_last_page for c in self.results):
            return False

        for c in self.results:  # noqa: SIM110
            # This may perform an COUNT query or read the results and detect the sentinel object:
            if c.has_next:
                return True
        return False

    def __iter__(self):
        return iter(self.results)
