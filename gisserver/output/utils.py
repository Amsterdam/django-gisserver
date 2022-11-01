from __future__ import annotations

from collections import defaultdict
from itertools import islice
from typing import Iterable, TypeVar

from django.db import models
from lru import LRU

M = TypeVar("M", bound=models.Model)

DEFAULT_SQL_CHUNK_SIZE = 2000  # allow unit tests to alter this.


class CountingIterator(Iterable[M]):
    """A simple iterator that counts how many results are given."""

    def __init__(self, iterator: Iterable[M]):
        self._iterator = iterator
        self._number_returned = 0
        self._in_iterator = False

    def __iter__(self):
        # Count the number of returned items while reading them.
        # Tried using map(itemgetter(0), zip(model_iter, count_iter)) but that's not faster.
        self._in_iterator = True
        try:
            self._number_returned = 0
            for instance in self._iterator:
                self._number_returned += 1
                yield instance
        finally:
            self._in_iterator = False

    @property
    def number_returned(self) -> int:
        """Tell how many objects the iterator processed"""
        if self._in_iterator:
            raise RuntimeError("Can't read number of returned results during iteration")
        return self._number_returned


class ChunkedQuerySetIterator(Iterable[M]):
    """An optimal strategy to perform ``prefetch_related()`` on large datasets.

    It fetches data from the queryset in chunks,
    and performs ``prefetch_related()`` behavior on each chunk.

    Django's ``QuerySet.prefetch_related()`` works by loading the whole queryset into memory,
    and performing an analysis of the related objects to fetch. When working on large datasets,
    this is very inefficient as more memory is consumed. Instead, ``QuerySet.iterator()``
    is preferred here as it returns instances while reading them. Nothing is stored in memory.
    Hence, both approaches are fundamentally incompatible. This class performs a
    mixed strategy: load a chunk, and perform prefetches for that particular batch.

    As extra performance benefit, a local cache avoids prefetching the same records
    again when the next chunk is analysed. It has a "least recently used" cache to avoid
    flooding the caches when foreign keys constantly point to different unique objects.
    """

    def __init__(self, queryset: models.QuerySet, chunk_size=None, sql_chunk_size=None):
        """
        :param queryset: The queryset to iterate over, that has ``prefetch_related()`` data.
        :param chunk_size: The size of each segment to analyse in-memory for related objects.
        :param sql_chunk_size: The size of each segment to fetch from the database,
            used when server-side cursors are not available. The default follows Django behavior.
        """
        self.queryset = queryset
        self.sql_chunk_size = sql_chunk_size or DEFAULT_SQL_CHUNK_SIZE
        self.chunk_size = chunk_size or self.sql_chunk_size
        self._fk_caches = defaultdict(lambda: LRU(self.chunk_size // 2))
        self._number_returned = 0
        self._in_iterator = False

    def __iter__(self):
        # Using iter() ensures the ModelIterable is resumed with the next chunk.
        self._number_returned = 0
        self._in_iterator = True
        try:
            qs_iter = iter(self.queryset.iterator(chunk_size=self.sql_chunk_size))

            # Keep fetching chunks
            while True:
                instances = list(islice(qs_iter, self.chunk_size))
                if not instances:
                    break

                # Perform prefetches on this chunk:
                if self.queryset._prefetch_related_lookups:
                    self._add_prefetches(instances)

                # And return to parent loop
                yield from instances
                self._number_returned += len(instances)
        finally:
            self._in_iterator = False

    @property
    def number_returned(self) -> int:
        """Tell how many objects the iterator processed"""
        if self._in_iterator:
            raise RuntimeError("Can't read number of returned results during iteration")
        return self._number_returned

    def _add_prefetches(self, instances: list[M]):
        """Merge the prefetched objects for this batch with the model instances."""
        if self._fk_caches:
            # Make sure prefetch_related_objects() doesn't have
            # to fetch items again that infrequently changes.
            all_restored = self._restore_caches(instances)
            if all_restored:
                return

        # Reuse the Django machinery for retrieving missing sub objects.
        # and analyse the ForeignKey caches to allow faster prefetches next time
        models.prefetch_related_objects(
            instances, *self.queryset._prefetch_related_lookups
        )
        self._persist_prefetch_cache(instances)

    def _persist_prefetch_cache(self, instances):
        """Store the prefetched data so it can be applied to the next batch"""
        for instance in instances:
            for lookup, obj in instance._state.fields_cache.items():
                if obj is not None:
                    cache = self._fk_caches[lookup]
                    cache[obj.pk] = obj

    def _restore_caches(self, instances) -> bool:
        """Restore prefetched data to the new set of instances.
        This avoids unneeded prefetching of the same ForeignKey relation.
        """
        if not instances:
            return True
        if not self._fk_caches:
            return False

        all_restored = True

        for lookup, cache in self._fk_caches.items():
            field = instances[0]._meta.get_field(lookup)
            for instance in instances:
                id_value = getattr(instance, field.attname)
                if id_value is None:
                    continue

                obj = cache.get(id_value, None)
                if obj is not None:
                    instance._state.fields_cache[lookup] = obj
                else:
                    all_restored = False

        return all_restored
