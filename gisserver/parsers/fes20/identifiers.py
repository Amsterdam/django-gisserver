"""These classes map to the FES 2.0 specification for identifiers.
The class names are identical to those in the FES spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from django.db.models import Q

from gisserver import conf
from gisserver.exceptions import ExternalValueError
from gisserver.parsers.ast import BaseNode, expect_no_children, expect_tag, tag_registry
from gisserver.parsers.values import auto_cast, parse_iso_datetime
from gisserver.parsers.xml import xmlns

NoneType = type(None)


class VersionActionTokens(Enum):
    """Values for the 'version' attribute of the ResourceId node."""

    FIRST = "FIRST"
    LAST = "LAST"
    ALL = "ALL"
    NEXT = "NEXT"
    PREVIOUS = "PREVIOUS"


class Id(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = xmlns.fes20

    #: Tell which the type this ID belongs to, needs to be overwritten.
    type_name = ...  # need to be defined by subclass!

    def build_query(self, compiler) -> Q:
        raise NotImplementedError()


@dataclass
@tag_registry.register("ResourceId")
class ResourceId(Id):
    """The <fes:ResourceId> element.
    This element allow queries to retrieve a resource by their identifier.
    """

    rid: str
    version: int | datetime | VersionActionTokens | NoneType = None
    startTime: datetime | None = None
    endTime: datetime | None = None

    def __post_init__(self):
        try:
            self.type_name, self.id = self.rid.rsplit(".", 1)
        except ValueError:
            if conf.GISSERVER_WFS_STRICT_STANDARD:
                raise ExternalValueError("Expected typename.id format") from None

            # This should end in a 404 instead.
            self.type_name = None
            self.id = None

    @classmethod
    @expect_tag(xmlns.fes20, "ResourceId")
    @expect_no_children
    def from_xml(cls, element):
        version = element.get("version")
        startTime = element.get("startTime")
        endTime = element.get("endTime")

        if version:
            version = auto_cast(version)

        return cls(
            rid=element.get_attribute("rid"),
            version=version,
            startTime=parse_iso_datetime(startTime) if startTime else None,
            endTime=parse_iso_datetime(endTime) if endTime else None,
        )

    def build_query(self, compiler=None) -> Q:
        """Render the SQL filter"""
        if self.startTime or self.endTime or self.version:
            raise NotImplementedError(
                "No support for <fes:ResourceId> startTime/endTime/version attributes"
            )

        lookup = Q(pk=self.id or self.rid)
        if compiler is not None:
            # When the
            # NOTE: type_name is currently read by the IdOperator that contains this object,
            # This code path only happens for stand-alone KVP invocation.
            compiler.add_lookups(lookup, type_name=self.type_name)
        return lookup
