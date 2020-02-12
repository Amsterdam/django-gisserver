# django-gisserver

Django speaking WFS 2.0 to expose geo data.

## Features

* WFS 2.0 simple implementation.
* GML 3.2 output.
* GeoJSON export support.
* Extensible view/operations.
* Uses GeoDjango queries for filtering.
* Uses Django template engine for rendering XML (might become streaming lxml later).

## Standards compliance

Currently, the following 3 methods are implemented:

* `GetCapabilities`
* `DescribeFeatureType`
* `GetFeature` with bbox and pagination support.

This is sufficient to show results in QGis.
The unit tests validate the output against WFS XSD schema.

Some parts for conformance to the "WFS simple" level are not implemented yet:

* `GetPropertyValue`
* `ListStoredQueries`
* `DescribeStoredQueries`
* `GetFeature` operation with only the `StoredQuery` action.
* Certain parameters:
  * Filtering: `filter`, `filter_language`, `resourceID`, `propertyName`
  * Resolving: `resolve`, `resolveDepth`, `resolveTimeout`
  * Output rewriting: namespaces, aliases
  * Some `GetCapabilities` features: `acceptFormats` and `sections`

Filtering is high on the TO-DO list.

### Low-prio items:

Anything outside WFS simple could be implemented, but is very low on the todo-list:

* The methods for the WFS basic, transactional, locking and inheritance conformance classes.
* HTTP POST requests.
* SOAP requests.

Nor supported are:

* Other protocols (WMS, WMTS, WCS)
* Other output formats (shapefile, CSV, KML, GML 3.1) - but easy to add.

## Why this code is shared

The "datapunt" team of the Municipality of Amsterdam develops software for the municipality.
Much of this software is then published as Open Source so that other municipalities,
organizations and citizens can use the software as a basis and inspiration to develop
similar software themselves. The Municipality of Amsterdam considers it important that
software developed with public money is also publicly available.

This package is initially developed by the City of Amsterdam, but the tools
and concepts created in this project can be used in any city.
