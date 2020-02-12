from gisserver.features import BoundingBox


class TestBoundingBox:
    def test_parse_4(self):
        bbox = BoundingBox.from_string("-1,-2,3,4")
        assert bbox.lower_corner == [-1, -2]
        assert bbox.upper_corner == [3, 4]

    def test_parse_5(self):
        bbox = BoundingBox.from_string("-1,-2,3,4,urn:ogc:def:crs:EPSG::28992")
        assert bbox.lower_corner == [-1, -2]
        assert bbox.upper_corner == [3, 4]
        assert bbox.crs.srid == 28992

    def test_extend(self):
        bbox = BoundingBox(1, 2, 3, 4)
        bbox.extend_to(-4, -3, -2, -1)
        assert bbox.lower_corner == [-4, -3]
        assert bbox.upper_corner == [3, 4]
