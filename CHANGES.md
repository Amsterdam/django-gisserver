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
