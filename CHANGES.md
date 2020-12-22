# 2020-12-22 (1.1.2)

* Fixed double ``>`` sign in ``<Filter xml..>>`` code when namespaces were auto-corrected.
* Fixed basic ``<Beyond>`` support for distance queries.
* Fixed parameter name for ``round()`` function.


# 2020-08-19 (1.1.1)

* Improve HTML page with "Using This WFS" section.
* Fixed Django 3.1 compatibility.
* Improved error message for `<fes:PropertyIsLike>` operator when comparing against a `<fes:ValueReference>` instead of `<fes:Literal>`.


# 2020-08-13 (1.1)

* Added browsable HTML views for WFS views, which can be extended/overwritten.
* Added content-disposition header to export formats, to have a proper filename.
* Added "abstract" property to field classes to provide a description.
* Consider `?SERVICE=WFS` as default for `WFSView` views.


# 2020-07-21 (1.0)

* Added `FeatureType.show_name_field` to show/hide `<gml:name>` and GeoJSON `geometry_name`.
* Added `FeatureType.xml_prefix` so the outputted namespace prefix can be changed from "app:" to anything else.
* Added `FeatureType.xsd_type_class` so this can be overwritten easier.
* Added `XsdNode.to_python()` to support input data parsing.
* Added `GISSERVER_SUPPORTED_CRS_ONLY` to accept only the listed coordinate systems.
* Rename `is_gml` -> `is_geometry`.
* Fixes for CITE compliance testing for WFS Basic conformance:
  * Added `ImplementsBasicWFS` flag in capabilities document.
  * Added attribute resolving, like `@gml:id` in XPath.
  * Added querying support for the `gml:name` field.
  * Added support to fetch multiple RESOURCEID objects in a single request.
  * Fixed unwanted exception when the RESOURCEID format is invalid, empty results are returned instead.
  * Fixed locator for RESOURCEID errors.
  * Fixed filter type exception, now `OperationParsingFailed` instead of `InvalidParameterValue`.
  * Fixed datetime and boolean comparisons.
  * Fixed exception message when `<PropertyIsLessThanOrEqualTo>` receives an GML object.
  * Fixed exception message for bad SRID's.
* Internal code reorganizations.


# 2020-07-09 (0.9.1)

* Fixed `GetPropertyValue` calls for non-db optimized rendering.


# 2020-07-09 (0.9)

* Added support for nested, flattened fields.
* Added support for dotted-names in field names.
* Added support for dotted-names in `model_attribute`.
* Added `GISSERVER_WRAP_FILTER_DB_ERRORS` setting for debugging filter errors.
* Added API's for easier subclassing:
  * `FeatureField.xsd_element_class`.
  * `FeatureField.parent` for elements in a complex feature.
  * `gisserver.features.get_basic_field_type()`.
* Fixed CSV output to render datetimes as UTC, identical to GeoJSON
* Fixed bugs found by CITE compliance testing:
  * Fixed support for LIKE operators on string-based foreign keys.
  * Fixed `<fes:PropertyIsLike>` on numeric values, when the field is a string.
  * Fixed comparison of `<fes:PropertyIs..>` when the field name and value are reversed.
* Improved error messages when using invalid comparison operators.
* Optimize feature retrieval, only fetch the actual fields being displayed.
* Compactified XML output headers.


# 2020-07-06 (0.8.4)

* Added field renaming support with `field(..., model_attribute=...)`.
* Added support for WFS 1 parameters TYPENAME and MAXFEATURES.
* Improved error handling for FES filters with invalid comparisons.
* Fixed GeoJSON support for Decimal/gettext\_lazy values.
* Fixes for CITE compliance testing for WFS Basic conformance:
  * Handle `NAMESPACES` parameter.
  * Fix missing "application/gml+xml" output format for `GetFeature`.
  * Fix namespace prefix support in filters (by stripping them).
  * Fix support for `<fes:BBOX>` with a single operand.
  * Fix `DescribeStoredQueries` to show the actual requested queries.
  * Fix `DescribeFeatureType` compliance testing by supporting the WFS 1 TYPENAME parameter.
  * Fix `GetFeatureById` response, which missed an xmlns:xsi to parse responses with "xsi:nil" values.
  * Fix `GetFeatureById` to return a 404 instead of 400 for any ID syntax, including unexpected formats.
  * Fix `GetCapabilities` by exposing "resolve=local" parameter.
  * Fix exposed WFS capabilities to pass cite WFS Simple conformance
* Fixed SORTBY parameter to handle renamed fields.


# 2020-06-30 (0.8.3)

* Added `GISSERVER_CAPABILITIES_BOUNDING_BOX` setting.
* Added `PropertyIsNull` support (though currently identical to `PropertyIsNil`).
* Fixed `DescribeFeatureType` to return all types when TYPENAMES is not provided.
* Advertise `ImplementsMinimumXPath` in `GetCapabilities` for cite testing (other servers also do this while being incomplete).


# 2020-06-30 (0.8.2)

* Improve XPath matching support, allow "app:" prefix and root elements.
* Refactored `FeatureType.resolve_element()` to return an `XPathMatch` object


# 2020-06-29 (0.8.1)

* Added unpaginated GeoJSON support (performance is good enough).
* Added basic support for non-namespaced `FILTER` queries, and `PropertyName` tags (though being WFS2 attributes, clients still use them).
* Added extra strict check that `ValueReference`/`Literal`/`ResourceId` nodes don't have child nodes.
* Fixed allowing filtering on unknown or undefined fields (XPaths are now resolved to known elements).
* Optimized results streaming by automatically using a queryset-iterator if possible.
* Optimized GeoJSON output by no longer selecting the other geometry fields.
* Added shortcut properties to `XsdComplexType`: `gml_elements` and `complex_elements`.


# 2020-06-25 (0.8)

* Added preliminary support to render complex field types (e.g. relations).
* Added `FeatureType.check_permissions()` hook to allow permission checking by subclasses.
* Added `WFSMethod.validate()` hook that allows request validation.
* Added CSV output format support.
* Added infinite pagination support.
* Added pagination size settings: `GISSERVER_DEFAULT_MAX_PAGE_SIZE`, `GISSERVER_CSV_MAX_PAGE_SIZE`.
* Added internal `XsdComplexType` class to support complex data schema definitions.
* Replaced many `FeatureType` methods to create a stable fields definition API.
* Replaced `FeatureType.fields_with_type` with `FeatureType.xsd_type` that returns an `XsdComplexType`.
* Optimized `GetFeature` responses by omitting a `COUNT` query for the last page.
* Optimized `GetFeature` responses by omitting the binary geometry data for DB-optimized rendering.
* Changed default page size / `DefaultMaxFeatures` to 5000.
* Fixed detecting `AutoField` as integer for Django 2.2.
* Fixed fallback datatype for unknown model fields (should be `xsd:anyType`, not `xsd:any` which is an element).
* Fixed fallback datatype for unknown geometry fields (should be `gml:GeometryPropertyType`, not gml:AbstractGeometryType).
* Fixed error messages for currently unsupported multiple-query KVP requests (e.g. `TYPENAMES=(A)(B)`).
* Fixed raising `InvalidParameterValue` for runtime errors in a custom `WFSView.get_feature_types()` implementation.
* Enforce using keyword-arguments on `FeatureType(...)`
* Internal code reorganizations/cleanups.


# 2020-06-08 (0.7)

* Added database-based rendering for GML/GeoJSON (disable with `GISSERVER_USE_DB_RENDERING=False`).
* Added `has_custom_backend` to CRS class.
* Improved rendering performance for python-based GML output.
* Improved `DescribeFeatureType` to show which geometry type is used in a geometry field.
* Fixed XML output error for pagination.
* Internal code reorganizations/cleanups.

# 2020-05-14 (0.6)

* Added `RESOURCEID` parameter support.
* Added `GetFeatureById` support.
* Added basic support for defining stored procedures.
* Added GML rendering for Polygon / MultiGeometry / MultiLineString / MultiPoint / LineString / LinearRing data.
* Fix `<fes:ResourceId>` parsing and type selection.
* Fix output errors because of `AttributeError` in `ForeignKey` fields.
* Fix `DateTimeField` being represented by an `xs:date` instead of `xs:dateTime`.
* Internal code reorganizations/cleanups.

# 2020-03-23 (0.5)

* Added `GetPropertyValue` support.
* Added empty `ListStoredQueries`/`DescribeStoredQueries` operations nearing Simple WFS conformance.
* Added a lot of built-in FES functions.
* Added `FeatureType(fields=...)` to limit which fields are exposed (can also use `__all__`).
* **Backwards incompatible:** by default no fields are exposed, unless they are mentioned.
* Added pagination links to GeoJSON response, based on WFS 3.0 DRAFT.
* Changed `max_page_size` to reasonable 1000 per page.
* Fixed `SRSNAME` support on GeoJSON output to select the coordinate reference system.
* Fixed `ResourceId` to extract the ID from the typename.id value.
* Improved performance of output streaming (buffering output, reducing yield).
* Removed lxml dependency, as it's only used for tests.
* Internal code reorganizations/cleanups.

# 2020-03-11 (0.4)

* Added response streaming for GML/GeoJSON.
* Added `OutputFormat(..., renderer_class=...)` API to integrate custom output formats.
* Added `SORTBY` parameter support.
* Fixed mentioning GML 3.2 instead of 3.1.1 in `GetCapabilities`.
* Fixed exposing FES filter capabilities for `GetCapabilities` request.
* Fixed error reporting for filter XML that were omitted.
* Fixed BBOX and FILTER to be mutually exclusive, as the spec requests.
* Fixed ISO formatting for date/datetime/time.
* Reverted BBOX operator to intersects (is more correct).
* Internal code reorganizations.

# 2020-03-09 (0.3)

* Added FES filtering support.
* Changed BBOX lookup operator to bboverlaps (uses PostGIS && operator).
* Improve field type reporting in DescribeFeatureType.

# 2020-02-24 (0.2)

* Added `CRS.from_srid()` function
* Added `CRS.apply_to()` API for geometry transformation.
* Added `CRS.backend` setting, which allows assigning a PROJ.4 string to the CRS object.
* Added support for other geometry types besides `Point` (affected `BoundingBox.extend_to_geometry()` and GeoJSON output).
* Added Python 3.6 support.
* Improved repeated geometry transformation speed, by using/caching `CoordTransform` objects.
* Fixed calling `BoundingBox.extend_to_geometry()` when crs parameter is not set.
* Changed `FeatureType` parameter from `model` to `queryset`.
* Replaced `ujson` with `orjson` for faster and better decimal support.

# 2020-02-12 (0.1)

* First basic release that works in QGis.
* Features:

 * WFS `GetCapabilities`
 * WFS `DescribeFeatureType`
 * WFS `GetFeature` with bbox and pagination support.
