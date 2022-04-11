from gisserver.geometries import CRS

WFS_NS = "http://www.opengis.net/wfs/2.0"
OWS_NS = "http://www.opengis.net/ows/1.1"
XLINK_NS = "http://www.w3.org/1999/xlink"
NAMESPACES = {
    "app": "http://example.org/gisserver",
    "gml": "http://www.opengis.net/gml/3.2",
    "ows": "http://www.opengis.net/ows/1.1",
    "wfs": "http://www.opengis.net/wfs/2.0",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}

RD_NEW_SRID = 28992  # https://epsg.io/28992

RD_NEW = CRS.from_string("urn:ogc:def:crs:EPSG::28992")
