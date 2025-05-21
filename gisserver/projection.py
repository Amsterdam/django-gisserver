"""In WFS, a "projection" is placed on top of the queried data.

It translates the incoming data into the subset of properties to display.
Practically, this code does inform and adjust the constructed QuerySet
to make sure it will provide only the actual fields that are part of the projection.
"""

from __future__ import annotations

import itertools
import logging
import operator
import typing
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

from gisserver.types import (
    GeometryXsdElement,
    XPathMatch,
    XsdElement,
    XsdNode,
    XsdTypes,
    _XsdElement_WithComplexType,
)

if typing.TYPE_CHECKING:
    from django.contrib.gis.geos import GEOSGeometry
    from django.db import models

    from gisserver.crs import CRS
    from gisserver.features import FeatureType
    from gisserver.parsers import fes20, wfs20

__all__ = (
    "FeatureProjection",
    "FeatureRelation",
)

logger = logging.getLogger(__name__)


class FeatureProjection:
    """Tell which fields to access and render for a single feature.
    This is inspired on 'fes:AbstractProjectionClause'.

    Instead of walking over the full XSD object tree,
    this object wraps that and makes sure only the actual requested fields are used.
    When a ``PROPERTYNAME`` (or ``<wfs:PropertyName>``) is used in the request,
    this will limit which fields to retrieve, which to prefetch, and which to render.
    """

    #: Referencing the Feature that is rendered.
    feature_type: FeatureType

    #: The list of root element to render for this feature.
    xsd_root_elements: list[XsdElement]

    #: The subset of child nodes to render for a given element.
    xsd_child_nodes: dict[XsdElement | None, list[XsdElement]]

    #: The output Coordinate Reference System
    output_crs: CRS

    #: Whether the output should be rendered without wrapper tags (for GetFeatureById).
    output_standalone: bool

    def __init__(
        self,
        feature_types: list[FeatureType],
        property_names: list[wfs20.PropertyName] | None = None,
        value_reference: fes20.ValueReference | None = None,
        output_crs: CRS | None = None,
        output_standalone: bool = False,
    ):
        """

        :param feature_types: The feature types used by this query. Typically one, unless there is a JOIN.
        :param property_names: Limited list of fields to render only.
        :param value_reference: Single element to display fo GetPropertyValue
        :param output_crs: Which coordinate reference system to use for geometry data.
        :param output_standalone: Used for the ``GetFeatureById`` stored query.
            This removes the ``wfs:FeatureCollection><wfs:member>`` wrapper elements from the output.
        """
        self.feature_types = feature_types
        self.feature_type = feature_types[0]  # JOIN still not supported.
        self.property_names = property_names
        self.value_reference = value_reference
        self.output_crs: CRS = output_crs or self.feature_type.crs
        self.output_standalone = output_standalone  # for GetFeatureById
        self._extra_matches = []

        if property_names:
            # Only a selection of the tree will be rendered.
            # Discover which elements should be rendered.
            child_nodes = self._get_child_nodes_subset()
            self.xsd_root_elements = child_nodes.pop(None)  # Pop it to avoid recursion risks
            self.xsd_child_nodes = child_nodes
        else:
            # All elements of the tree will be rendered, retrieve all elements.
            # Note xsd_child_nodes can be altered below, so don't assign it a cached property.
            self.xsd_root_elements = self.feature_type.xsd_type.elements_including_base
            self.xsd_child_nodes = {
                node: node.type.elements
                for node in self.feature_type.xsd_type.all_complex_elements
            }

    def _get_child_nodes_subset(self) -> dict[XsdElement | None, list[XsdElement]]:
        """Translate the PROPERTYNAME into a dictionary of nodes to render."""
        child_nodes = defaultdict(list)
        for xpath_match in self.xpath_matches:
            # Make sure the tree is known beforehand, and it has no duplicate parent nodes.
            # (e.g. PROPERTYNAME=node/child1,node/child2)
            parent = None
            for xsd_node in xpath_match.nodes:
                if xsd_node not in child_nodes[parent]:
                    child_nodes[parent].append(xsd_node)
                parent = xsd_node

        return dict(child_nodes)

    def add_field(self, xsd_element: XsdElement):
        """Restore the retrieval of a field that was not asked for in the original query."""
        if xsd_element.type.is_complex_type:
            raise NotImplementedError("Can't restore nested elements right now")
        if not self.property_names or xsd_element in self.xsd_root_elements:
            return

        logger.debug("Projection: added %s", xsd_element)
        self.xsd_root_elements.append(xsd_element)
        self._extra_matches.append(XPathMatch(self.feature_type, [xsd_element], ""))
        _clear_cached_properties(self)

    def remove_fields(self, predicate: Callable[[XsdElement], bool]):
        """Remove elements from the projection based on a given rule.
        This helps to remove M2M and Array elements for CSV output for example.

        Make sure this function is called as early as possible,
        before other logic already read these attributes.
        """
        self.xsd_root_elements, removed_nodes = _partition(predicate, self.xsd_root_elements)

        for xsd_child_root, xsd_child_elements in self.xsd_child_nodes.items():
            if xsd_child_root in removed_nodes:
                continue  # already removed the top-level, don't bother checking here

            keep_children, remove_children = _partition(predicate, xsd_child_elements)
            self.xsd_child_nodes[xsd_child_root] = keep_children
            removed_nodes.update(remove_children)

        # Remove complete trees if their parent was removed.
        for xsd_child_root in list(self.xsd_child_nodes):
            if xsd_child_root in removed_nodes:
                self.xsd_child_nodes.pop(xsd_child_root, None)

        if logger.isEnabledFor(logging.DEBUG) and removed_nodes:
            logger.debug("Projection: removed %s", removed_nodes)

        _clear_cached_properties(self)

    @cached_property
    def _geometry_getter(self):
        return operator.attrgetter(self.main_geometry_element.orm_path)

    def get_main_geometry_value(self, instance: models.Model) -> GEOSGeometry | None:
        """Efficiently retrieve the value for the main geometry element."""
        if self.main_geometry_element is None:
            return None
        else:
            return self._geometry_getter(instance)

    @cached_property
    def xpath_matches(self) -> list[XPathMatch]:
        """Resolve which elements the property names point to"""
        if not self.property_names:
            raise RuntimeError("This method is only useful for propertyname projections.")

        return [
            self.feature_type.resolve_element(property_name.xpath, property_name.xpath_ns_aliases)
            for property_name in self.property_names
        ] + self._extra_matches

    @cached_property
    def all_elements(self) -> list[XsdElement]:
        """Return ALL elements of all levels to render."""
        return self.xsd_root_elements + list(
            itertools.chain.from_iterable(self.xsd_child_nodes.values())
        )

    @cached_property
    def all_geometry_elements(self) -> list[GeometryXsdElement]:
        """Tell which GML elements will be hit."""
        return [e for e in self.all_elements if e.type.is_geometry]

    @cached_property
    def all_complex_elements(self) -> list[_XsdElement_WithComplexType]:
        """Return ALL tree elements with a complex type, including child elements with a complex types."""
        return list(self.xsd_child_nodes.keys())

    @cached_property
    def all_flattened_elements(self) -> list[XsdElement]:
        """Shortcut to get ALL tree elements with a flattened model attribute"""
        if not self.property_names:
            return self.feature_type.xsd_type.flattened_elements
        else:
            return [e for e in self.all_elements if e.is_flattened]

    @cached_property
    def has_bounded_by(self) -> bool:
        """Tell whether the <gml:boundedBy> element is included for rendering."""
        return any(e.type is XsdTypes.gmlBoundingShapeType for e in self.xsd_root_elements)

    @cached_property
    def main_geometry_element(self) -> GeometryXsdElement | None:
        """Return the field used to describe the geometry of the feature.
        When the projection excludes the geometry, ``None`` is returned.
        """
        geo_element = self.feature_type.main_geometry_element
        if self.property_names and geo_element not in self.all_elements:
            return None

        return geo_element

    @cached_property
    def geometry_elements(self) -> list[GeometryXsdElement]:
        """Tell which GML elements will be hit at the root-level."""
        return [
            e
            for e in self.xsd_root_elements
            if e.type.is_geometry and e.type is not XsdTypes.gmlBoundingShapeType
        ]

    @cached_property
    def property_value_node(self) -> XsdNode:
        """For GetPropertyValue, resolve the element that is rendered."""
        if self.value_reference is None:
            raise RuntimeError("This method is only useful for GetPropertyValue calls.")
        return (
            self.feature_types[0]
            .resolve_element(self.value_reference.xpath, self.value_reference.xpath_ns_aliases)
            .child
        )

    @cached_property
    def orm_relations(self) -> list[FeatureRelation]:
        """Tell which fields will be retrieved from related fields.

        This gives an object layout based on the XSD elements,
        that can be used for prefetching data.
        """
        related_models: dict[str, type[models.Model]] = {}
        fields: dict[str, set[XsdElement]] = defaultdict(set)
        elements = defaultdict(list)

        # Check all elements that render as "dotted" flattened relation
        for xsd_element in self.all_flattened_elements:
            if xsd_element.source is not None:
                # Split "relation.field" notation into path, and take the field as child attribute.
                obj_path, field = xsd_element.orm_relation
                elements[obj_path].append(xsd_element)
                fields[obj_path].add(xsd_element)
                # field is already on relation:
                related_models[obj_path] = xsd_element.source.model

        # Check all elements that render as "nested" complex type:
        for xsd_element in self.all_complex_elements:
            # The complex element itself points to the root of the path,
            # all sub elements become the child attributes.
            obj_path = xsd_element.orm_path
            elements[obj_path].append(xsd_element)
            fields[obj_path] = {
                f
                for f in self.xsd_child_nodes[xsd_element]
                if not f.is_many or f.is_array  # exclude M2M, but include ArrayField
            }
            if xsd_element.source:
                # field references a related object:
                related_models[obj_path] = xsd_element.source.related_model

        return [
            FeatureRelation(
                orm_path=obj_path,
                sub_fields=sub_fields,
                related_model=related_models.get(obj_path),
                xsd_elements=elements[obj_path],
            )
            for obj_path, sub_fields in fields.items()
        ]

    @cached_property
    def only_fields(self) -> list[str]:
        """Tell which fields to limit the queryset to.
        This excludes M2M fields because those are not part of the local model data.
        """
        if self.property_names is not None:
            return [
                # TODO: While ORM rel__child paths can be passed to .only(),
                # these may not be accurately applied to foreign keys yet.
                # Also, this is bypassed by our generated Prefetch() objects.
                xpath_match.orm_path
                for xpath_match in self.xpath_matches
                if not xpath_match.is_many or xpath_match.child.is_array
            ]
        else:
            # Also limit the queryset to the actual fields that are shown.
            # No need to request more data
            return [
                f.orm_field
                for f in self.feature_type.xsd_type.elements
                if not f.is_many or f.is_array  # avoid M2M fields for .only(), but keep ArrayField
            ]


@dataclass
class FeatureRelation:
    """Tell which related fields are queried by the feature."""

    #: The ORM path that is queried for this particular relation
    orm_path: str
    #: The fields that will be retrieved for that path (limited by the projection)
    sub_fields: set[XsdElement]
    #: The model that is accessed for this relation (if set)
    related_model: type[models.Model] | None
    #: The source elements that access this relation. Could be multiple for flattened relations.
    xsd_elements: list[XsdElement]

    @cached_property
    def _local_model_field_names(self) -> list[str]:
        """Tell which local fields of the model will be accessed by this feature."""
        return [
            model_field.name
            for field in self.sub_fields
            if not (model_field := field.source).many_to_many and not model_field.one_to_many
        ] + self._local_backlink_field_names

    @property
    def _local_backlink_field_names(self) -> list[str]:
        # When this relation is retrieved through a ManyToOneRel (reverse FK),
        # the prefetch_related() also needs to have the original foreign key
        # in order to link all prefetches to the proper parent instance.
        return [
            xsd_element.source.field.name
            for xsd_element in self.xsd_elements
            if xsd_element.source is not None and xsd_element.source.one_to_many
        ]

    @property
    def geometry_elements(self) -> list[GeometryXsdElement]:
        """Tell which geometry elements this relation will access."""
        return [f for f in self.sub_fields if f.type.is_geometry]


def _partition(predicate, items: list) -> tuple[list, set]:
    """Semi-efficient way to split a list into items that match/don't match the condition."""
    # more_itertools.partition() is faster, but that can be neglected with a short list.
    return list(itertools.filterfalse(predicate, items)), set(filter(predicate, items))


def _clear_cached_properties(object):
    """Remove the caches from the cached_property decorator on an object."""
    cls = object.__class__
    for property_name in list(object.__dict__):
        if (prop := getattr(cls, property_name, None)) is not None and isinstance(
            prop, cached_property
        ):
            del object.__dict__[property_name]
