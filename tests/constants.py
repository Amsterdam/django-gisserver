from django.contrib.gis.gdal import SpatialReference

from gisserver.types import CRS

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

# These values come from postgis 2.5.3 on homebrew
RD_NEW_PROJ = (
    "+proj=sterea +lat_0=52.15616055555555 +lon_0=5.38763888888889 "
    "+k=0.9999079 +x_0=155000 +y_0=463000 +ellps=bessel "
    "+towgs84=565.2369,50.0087,465.658,-0.406857,0.350733,-1.87035,4.0812 "
    "+units=m +no_defs"
)
RD_NEW_WKT = (
    'PROJCS["Amersfoort / RD New",'
    'GEOGCS["Amersfoort",'
    'DATUM["Amersfoort",SPHEROID["Bessel 1841",6377397.155,299.1528128,AUTHORITY["EPSG","7004"]],'
    'TOWGS84[565.417,50.3319,465.552,-0.398957,0.343988,-1.8774,4.0725],AUTHORITY["EPSG","6289"]],'
    'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4289"]],'
    'PROJECTION["Oblique_Stereographic"],'
    'PARAMETER["latitude_of_origin",52.15616055555555],'
    'PARAMETER["central_meridian",5.38763888888889],'
    'PARAMETER["scale_factor",0.9999079],'
    'PARAMETER["false_easting",155000],'
    'PARAMETER["false_northing",463000],'
    'UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
    'AXIS["X",EAST],'
    'AXIS["Y",NORTH],'
    'AUTHORITY["EPSG","28992"]]'
)

RD_NEW = CRS.from_string(
    "urn:ogc:def:crs:EPSG::28992", backend=SpatialReference(RD_NEW_PROJ),
)
