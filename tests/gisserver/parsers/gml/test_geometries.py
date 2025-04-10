from gisserver.parsers.gml import GEOSGMLGeometry


class TestParseBBox:
    def test_parse_4(self):
        bbox = GEOSGMLGeometry.from_bbox("-1,-2,3,4")
        assert bbox.geos_data.extent == (-1.0, -2.0, 3.0, 4.0)
        assert bbox.geos_data.srid is None

    def test_parse_5(self):
        bbox = GEOSGMLGeometry.from_bbox("-1,-2,3,4,urn:ogc:def:crs:EPSG::28992")
        assert bbox.geos_data.extent == (-1.0, -2.0, 3.0, 4.0)
        assert bbox.srs.srid == 28992
