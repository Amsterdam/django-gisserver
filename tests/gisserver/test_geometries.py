from gisserver.geometries import BoundingBox


class TestBoundingBox:
    def test_extend(self):
        bbox = BoundingBox(1, 2, 3, 4)
        bbox.extend_to(-4, -3, -2, -1)
        assert bbox.lower_corner == [-4, -3]
        assert bbox.upper_corner == [3, 4]
