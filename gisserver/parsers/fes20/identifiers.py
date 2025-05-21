"""These classes map to the FES 2.0 specification for identifiers.
The class names are identical to those in the FES spec.

Inheritance structure:

* :class:`Id`

 * :class:`ResourceId`
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from django.db.models import Q

from gisserver import conf
from gisserver.exceptions import ExternalValueError, InvalidParameterValue
from gisserver.parsers.ast import AstNode, expect_no_children, expect_tag, tag_registry
from gisserver.parsers.values import auto_cast, parse_iso_datetime
from gisserver.parsers.xml import parse_qname, xmlns

NoneType = type(None)


class VersionActionTokens(Enum):
    """Values for the 'version' attribute of the :class:`ResourceId` node."""

    FIRST = "FIRST"
    LAST = "LAST"
    ALL = "ALL"
    NEXT = "NEXT"
    PREVIOUS = "PREVIOUS"


class Id(AstNode):
    """Abstract base class, as defined by FES spec.
    Any custom identifier-element needs to extend from this node.
    By default, the :class:`ResourceId` element is supported.
    """

    xml_ns = xmlns.fes20

    def get_type_name(self):
        raise NotImplementedError()

    def build_query(self, compiler) -> Q:
        raise NotImplementedError()


@dataclass
@tag_registry.register("ResourceId")
class ResourceId(Id):
    """The ``<fes:ResourceId>`` element.
    This element allow queries to retrieve a resource by their identifier.

    This parses the syntax::

        <fes:ResourceId rid="typename.123" />

    This element is placed inside a :class:`~gisserver.parsers.fes20.filters.Filter`.
    """

    #: A raw "resource identifier". It typically includes the object name,
    #: which is completely unrelated to XML namespacing.
    rid: str

    #: Internal extra attribute, referencing the inferred typename from the :attr:`rid`.
    type_name: str | None

    #: Unused, this is part of additional conformance classes.
    version: int | datetime | VersionActionTokens | NoneType = None
    startTime: datetime | None = None
    endTime: datetime | None = None

    def get_type_name(self):
        """Implemented/override to expose the inferred type name."""
        return self.type_name

    def __post_init__(self):
        if conf.GISSERVER_WFS_STRICT_STANDARD and "." not in self.rid:
            raise ExternalValueError("Expected typename.id format") from None

    @classmethod
    def from_string(cls, rid, ns_aliases: dict[str, str]):
        # Like GeoServer, assume the "name" part of the "resource id" is a QName.
        return cls(
            rid=rid,
            type_name=parse_qname(rid.rpartition(".")[0], ns_aliases),
        )

    @classmethod
    @expect_tag(xmlns.fes20, "ResourceId")
    @expect_no_children
    def from_xml(cls, element):
        version = element.get("version")
        startTime = element.get("startTime")
        endTime = element.get("endTime")

        if version:
            version = auto_cast(version)

        rid = element.get_str_attribute("rid")
        return cls(
            rid=rid,
            type_name=element.parse_qname(rid.rpartition(".")[0]),
            version=version,
            startTime=parse_iso_datetime(startTime) if startTime else None,
            endTime=parse_iso_datetime(endTime) if endTime else None,
        )

    def build_query(self, compiler) -> Q:
        """Render the SQL filter"""
        if self.startTime or self.endTime or self.version:
            raise NotImplementedError(
                "No support for <fes:ResourceId> startTime/endTime/version attributes"
            )

        object_id = self.rid.rpartition(".")[2]

        try:
            # The 'ID' parameter is typed as string, but here we can check
            # whether the database model needs an integer instead.
            compiler.feature_types[0].model._meta.pk.get_prep_value(object_id)
        except (TypeError, ValueError) as e:
            raise InvalidParameterValue(
                f"Invalid resourceId value: {e}", locator="resourceId"
            ) from e

        return Q(pk=object_id)
