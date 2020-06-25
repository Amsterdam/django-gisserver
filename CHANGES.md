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
