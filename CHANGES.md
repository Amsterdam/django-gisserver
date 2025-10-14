# 2025-10-14 (2.2.1)

* Add outputFormat to GetFeature operation to support ArcGISOnline

# 2025-09-18 (2.2.0)

* Drop support for python 3.9 and Django 3.2

# 2025-09-17 (2.1.4)

* Remove reference to bootstrap.min.css.map file

# 2025-09-16 (2.1.3)

* Add missing bootstrap.min.css.map file

# 2025-09-10 (2.1.2)

* Stop using CDN for bootstrap stylesheet, instead use a static local file.
  This in order for the server to work in an airgapped environment (PR#72).

# 2025-06-06 (2.1.1)

* Fixed using legacy longitude/latitude rendering for `EPSG:4326` and `:http://www.opengis.net/gml/srs/epsg.xml#xxxx` SRS names.
* Improved styling for the default HTML page.

This increases interoperability with web-based clients and legacy libraries. GeoServer applies the same heuristic.
Clients that use the official OGC notations such as `urn:ogc:def:crs:EPSG::4326` and `http://www.opengis.net/def/crs/epsg/0/4326`
are not affected. If needed, this behavior can be disabled using `GISSERVER_FORCE_XY_EPSG_4326=False` and `GISSERVER_FORCE_XY_OLD_CRS=False`.

# 2025-05-29 (2.1)

* Added support for `ArrayField` field in CSV exports.
* Added support for `models.DurationField` for features.
* Added proper axis ordering handling.
* Changed built-in fes functions to match current GeoServer signatures.
* Improved error handling for invalid filter input (also fixes 500 errors).
* Improved error handling for database query errors during rendering.
* Improved error messages for unexpected tags in the XML body.
* Improved error handling for fes 1.0 arithmetic operators (e.g. typing: `date > 2020-01-01` in QGis).
* Improved HTML index page, make it easier to override and restyle.
* Improved documentation, added API documentation.
* Fixed axis ordering handling for `EPSG:4326` and other longitude/latitude CRS definitions.
* Fixed comparing to `NULL` when date/time input is invalid.
* Fixed filter comparisons for `<`, `<=`, `>`, `>=` when using a reversed "value < property" ordering.
* Fixed crash when receiving WFS 1.0 POST requests.
* Fixed building readthedocs.

# 2025-04-28 (2.0)

* Added support for XML POST requests.
* Added support for geometry elements on child nodes.
* Added support for Django 5 `GeneratedField` fields as geometry field.
* Added `WFSView.check_permissions()` API to simplify permission checking.
* Added `WFSView.xml_namespace_aliases` attribute to configure custom namespace prefixes.
* Added example app and docker-compose setup for testing.
* Added `GISSERVER_EXTRA_OUTPUT_FORMATS` setting to define additional output formats.
* Added `GISSERVER_GET_FEATURE_OUTPUT_FORMATS` setting to override the default output formats.
* Added `CRS84` and `WEB_MERCATOR` constants in `gisserver.geometries`.
* Improved debugging by adding debug-level logging and better error messages.
* Improved font styling somewhat for browsable HTML pages.
* Fixed XML namespace support (e.g. handling `<ValueReference>ns0:tagname</ValueReference>`).
* Fixed bugs found by CITE compliance testing:
  * Support `<fes:PropertyIsLike>` for array elements.
  * Support `<fes:PropertyIsNil>` for geometry elements.
  * Support `resulttype=hits` with `count` arguments.
* Fixed `ArrayField` detection when `django.contrib.postgres` is not in `INSTALLED_APPS`.
* Fixed `main_geometry_element` detection.
* Fixed swapped X/Y coordinates for systems that use a different axis-ordering (e.g. EPSG:3879 for Finland).
* Fixed GeoJSON CRS value to be `CRS84` (urn:ogc:def:crs:OGC::CRS84) instead of WGS84 (urn:ogc:def:crs:EPSG::4326).
* Fixed applying the `CRS.backend` when the client requests a custom coordinate system using `srsName`.
* Fixed rendering JSON exceptions during streaming errors.
* Fixed internal XML Schema; use proper model CamelCasing for class names (doesn't affect requests).
* Fixed internal XML schema; remove unneeded inheritance from `gml:AbstractFeatureType` for nested elements.
* Fixed CI testing.
* Confirmed support for Python 3.13.

This release has a lot of API changes, renamed and moved classes,
which was needed to implement POST support and XML namespace handling.

This won't affect most projects as they use the basic `FeatureType` functionality.
For implementations that have taken full advantage of our architecture,
the notable API changes are:

* Configuration:
  * `WFSOperation.output_formats` still works, but `get_output_formats()` is preferred.
  * `WFSOperation.parameters` is replaced by ``get_parameters()`` and only lists parameters that need to be mentioned in `GetCapabilities`.
  * The `Parameter` class only exposes choices, parsing happens in `gisserver.parsers.wfs20` now.
  * `FeatureType.xml_namespace` now defines which namespace the feature exists in (defaults to `WFSView.xml_namespace`).
* Overiding and extending queries:
  * `FeatureType.get_extent()` was replaced with ``GmlBoundedByElement.get_value()``.
  * `gisserver.operations`: renamed `WFSMethod` -> `WFSOperation`.
  * `gisserver.extensions.functions` now tracks filter function registration.
  * `gisserver.extensions.queries` now tracks stored query registration.
  * The `StoredQuery` base class is now `StoredQueryImplementation` providing a `build_query()` method.
  * The internal `CompiledQuery` moved to `gisserver.parsers.query` and receives a `feature_types` array now with a single element.
   (This change reflects the WFS spec and allowing to potentially implement JOIN queries later).
* Request parsing:
  * `WFSView.ows_request` and `request.ows_request` both provide access to the parsed WFS request.
  * `WFSOperation.parser_class` allows to define a custom parser for a additional WFS operations.
  * The WFS request parsing moved to `gisserver.parsers.wfs20`, which builds an Abstract Syntax Tree (AST) of the XML request.
  * The GET request (KVP format) parsing is now a special-case of the XML-based parsing classes.
* Output formats:
  * `gisserver.output` no longer exposes the auto-switching DB/non-DB rendering aliases, as `get_output_formats()` can do that easier.
  * `OutputRenderer` only provides the basic XML aliasing, a new `CollectionOutputRenderer` base class provides the collection logic.
  * `OutputRenderer.xml_namespaces` allows defining XML namespace aliases that construct default `xmlns` attributes.
  * All rendering parameters (e.g. output CRS) moved to the `FeatureProjection` logic.
  * The `decorate_queryset()` logic is no longer a classmethod.
* Internal XSD schema elements:
  * XML tag parsing is reworked for simplicity and namespace handling.
  * Namespace aliases/prefixes are removed entirely, and resolved during rendering.
  * `FeatureType.xml_name` now returns the full XML name, not the QName.
  * `XsdTypes` use fully qualified XML names, not the QName.
  * `XsdElement.xml_name` now returns the full XML name, not the QName.
  * `XsdElement.is_geometry` was unneeded, use `XsdElement.type.is_geometry` now.
  * `XsdElement.orm_path` points to the absolute path, and `XsdElement.local_orm_path` to the relative path.

# 2024-11-25 (1.5.0)

* Added `PROPERTYNAME` support
* Added rendering of `<wfs:truncatedResponse>` when errors happen during output streaming.
* Fixed accessing a feature with 3 geometry fields (fixed our PostgreSQL `ST_Union` syntax).
* Make sure Django 4.1+ won't do double prefetches on relations that we prefetch.
* Hide the erroneous output formats in `GetCapabilities` that are supported for FME.
* Bump requirements to non-vulnerable versions (of lxml and orjson).
* Improved documentation.
* Cleaned up code, removing some internal methods.
* Cleaned up leftover Python 3.7 compat code.

# 2024-08-29 (1.4.1)

* Fix 500 error when `model_attribute` points to a dotted-path.
  PR thanks to [sposs](https://github.com/sposs).
* Updated pre-commit configuration and test matrix.

# 2024-07-01 (1.4.0)

* Added `GISSERVER_COUNT_NUMBER_MATCHED` setting to allow disabling "numberReturned" counting.
  This will avoid an expensive PostgreSQL COUNT query, speeding up returning large sets.
* Added basic support for array fields in `GetPropertyValue`.
* Optimized GML rendering performance (around 15-20% faster on large datasets).
* Optimized overall rendering performance, which improved GeoJSON/CSV output too.
* Developers: updated pre-commit hooks
* Cleaned up leftover Python 3.7 compat code.

# 2023-06-08 (1.3.0)

* Django 5 support added.

## Contributors

We would like to thank the following contributors
for their work on this release.

* [tomdtp](https://github.com/tomdtp)

# 2023-06-08 (1.2.7)

* WFS endpoints now accept a GML version number in their OUTPUTFORMAT.

# 2023-06-07 (1.2.6)

* Workaround for FME doing a DescribeFeatureType with the wrong outputformat.
* Dropped support for Django versions < 3.2 and Python < 3.9.
* Minor optimizations.

# 2023-01-11 (1.2.5)

* CRS parsing no longer raises SyntaxErrors.

# 2022-11-01 (1.2.4)

* Fixed type assertion when `django.contrib.postgres` was not installed.

# 2022-09-07 (1.2.3)

* Added "geojson" as output format alias in `GetCapabilities` for ESRI ArcGIS online.

# 2022-07-28 (1.2.2)

* Optimized response writing, buffering provement gave ~12-15% speedup.
* Optimized GML response, reduced response size by ~9% by removing whitespace.

# 2022-04-13 (1.2.1)

* Fixed regression for auto-correcting xmlns for `<Filter>` tags that have leading whitespace.
* Fixed weird crashes when geometry field is not provided.
* Simplify `FeatureType.geometry_field` logic.

# 2022-04-11 (1.2)

* Added support for `maxOccurs=unbounded` elements (M2M, reverse foreign key, array fields).
* Added support for filtering on M2M, reverse foreign key and array fields.
* Added `field(..., xsd_class=...)` parameter to simplify overriding `FeatureField.xsd_element_class`.
* Added `xsd_base_type` parameter to `ComplexFeatureField` to allow overriding it.
* Added `GISSERVER_DB_PRECISION` setting and made precision consistent between output formats.
* Added `.prefetch_related()` support to large GeoJSON responses (using prefetching on iterator chunks).
* Added `FeatureType.filter_related_queryset()` that allows adjusting all retrieved querysets.
* Using `.only()` to reduce transferred data to the actual fields.
* Optimized large responses through the chunked-iterator and `.only()` usage (seen 2x improvement on GeoJSON on some large datasets).
* Improved `<fes:Filter>` error handling, avoid internal server errors for missing XML child elements.
* Improved GeoJSON content type in HTTP responses, using `application/geo+json` instead of `application/json`.
* Fixed next/previous pagination links, to preserve lowercase querystring fields that project-specific code might use.
* Fixed preserving extra querystring fields in HTML pages.
* Fixed integration with custom fields, using `value_from_object()` instead of `getattr()` to retrieve field values.
* Fixed calculating extent over feature with mixed geometry types.
* Various code cleanups.
* Dropped Python 3.6 support.

# 2021-05-17 (1.1.3)

* Included Django 3.2 in test matrix.
* Fixed preserving axis orientation by passing Incoming SRS data is directly to GDAL.
* Fixed doc typoo's
* Updated pre-commit hooks.
* Drop universal wheel declaration (Python 2 is no longer supported)

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
* Added basic support for non-namespaced `FILTER` queries, and `PropertyName` tags (though being WFS1 attributes, clients still use them).
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
