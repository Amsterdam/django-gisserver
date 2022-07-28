"""Output buffering, to write data in chunks.

This builds on top of StringIO/BytesIO to write data and regularly flush it.
"""
from __future__ import annotations
from typing import Generic, TypeVar
import io

V = TypeVar("V", str, bytes)


class BaseBuffer(Generic[V]):
    """Fast buffer to write data in chunks.
    This avoids performing too many yields in the output writing.
    Especially for GeoJSON, that slows down the response times.
    """

    buffer_class = None

    def __init__(self, chunk_size=8192):
        self.data = self.buffer_class()
        self.chunk_size = chunk_size

    def is_full(self):
        # Calling data.seek() is faster than doing self.size += len(value)
        # because each integer increment is a new object allocation.
        return self.data.tell() >= self.chunk_size

    def write(self, value: V):
        if value is None:
            return
        self.data.write(value)

    def flush(self) -> V:
        """Empty the buffer and return it."""
        data = self.getvalue()
        self.clear()
        return data

    def getvalue(self) -> V:
        return self.data.getvalue()

    def clear(self):
        self.data.seek(0)
        self.data.truncate(0)


class BytesBuffer(BaseBuffer[bytes]):
    """Collect the data as bytes."""

    buffer_class = io.BytesIO

    def __bytes__(self):
        return self.getvalue()


class StringBuffer(BaseBuffer[str]):
    """Collect the data as string"""

    buffer_class = io.StringIO

    def __str__(self):
        return self.getvalue()
