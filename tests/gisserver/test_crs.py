import pytest
from django.contrib.gis.gdal import AxisOrder
from django.contrib.gis.geos import Point

from gisserver.crs import CRS, WGS84


class TestCRS:
    @pytest.mark.parametrize("input", [4326, "4326"])
    def test_from_srid(self, input):
        """Provide that the from_srid() uses modern notation"""
        crs = CRS.from_string(input)
        assert crs.origin is None
        assert not crs.force_xy
        assert crs.is_north_east_order
        assert str(crs) == "urn:ogc:def:crs:EPSG::4326"

    def test_from_string_modern(self):
        """Prove that modern notation works."""
        crs = CRS.from_string("urn:ogc:def:crs:EPSG::4326")
        assert crs.origin == "urn:ogc:def:crs:EPSG::4326"
        assert not crs.force_xy
        assert crs.axis_direction == ["north", "east"]
        assert crs.is_north_east_order

        # Test output formats
        assert crs.urn == "urn:ogc:def:crs:EPSG::4326"
        assert crs.legacy == "http://www.opengis.net/gml/srs/epsg.xml#4326"
        assert str(crs) == "urn:ogc:def:crs:EPSG::4326"

    @pytest.mark.parametrize(
        "force_xy,expect_str",
        [
            (False, "urn:ogc:def:crs:EPSG::4326"),
            (True, "http://www.opengis.net/gml/srs/epsg.xml#4326"),
        ],
        ids=["modern", "force_xy"],
    )
    def test_from_string_legacy_epsg(self, force_xy, settings, expect_str):
        """Prove that legacy notation has a legacy axis orientation by default."""
        settings.GISSERVER_FORCE_XY_OLD_CRS = force_xy
        settings.GISSERVER_FORCE_XY_EPSG_4326 = force_xy

        legacy = CRS.from_string("epsg:4326")
        assert legacy.origin == "EPSG:4326"
        assert legacy.force_xy == force_xy
        assert legacy.is_north_east_order  # not changed

        # Test output formats
        assert legacy.urn == "urn:ogc:def:crs:EPSG::4326"
        assert legacy.legacy == "http://www.opengis.net/gml/srs/epsg.xml#4326"
        assert str(legacy) == expect_str

    def test_from_string_legacy_uri(self, settings):
        settings.GISSERVER_FORCE_XY_EPSG_4326 = True
        legacy = CRS.from_string("epsg:4326")
        assert legacy.origin == "EPSG:4326"
        assert legacy.force_xy
        assert legacy.is_north_east_order  # not changed.

        # Test output formats
        assert legacy.urn == "urn:ogc:def:crs:EPSG::4326"
        assert legacy.legacy == "http://www.opengis.net/gml/srs/epsg.xml#4326"
        assert str(legacy) == "http://www.opengis.net/gml/srs/epsg.xml#4326"

    def test_crs84_inequal(self):
        """Prove that using strings from other vendors is also parsed."""
        crs84 = CRS.from_string("urn:ogc:def:crs:OGC:1.3:CRS84")
        assert crs84.srid == WGS84.srid

        # EPSG:4326 specifies coordinates in lat/long order and CRS:84 in long/lat order
        assert crs84 != WGS84

    def test_crs_empty_version(self):
        """Prove that empty versions are properly re-encoded as empty string"""
        assert CRS.from_string("urn:ogc:def:crs:EPSG::28992").urn == "urn:ogc:def:crs:EPSG::28992"

    @pytest.mark.parametrize(
        "modern_name", ["http://www.opengis.net/def/crs/epsg/0/4326", "urn:ogc:def:crs:EPSG::4326"]
    )
    @pytest.mark.parametrize("force_xy", [False, True], ids=["modern", "force_xy"])
    def test_legacy_to_modern_url(self, modern_name, settings, force_xy):
        settings.GISSERVER_FORCE_XY_OLD_CRS = force_xy
        settings.GISSERVER_FORCE_XY_EPSG_4326 = force_xy

        legacy_crs = CRS.from_string("EPSG:4326")
        modern_crs = CRS.from_string(modern_name)
        assert not modern_crs.force_xy

        if force_xy:
            # Resulting axes are different, so don't see is identical.
            assert legacy_crs.force_xy
            assert legacy_crs != modern_crs
        else:
            # Same output, treat is identical
            assert not legacy_crs.force_xy
            assert legacy_crs == modern_crs

        assert legacy_crs.srid == modern_crs.srid
        assert legacy_crs.urn == modern_crs.urn == "urn:ogc:def:crs:EPSG::4326"

    def test_axis_order_custom(self):
        """Prove that custom axis ordering is applied."""
        rd_point = Point(121400, 487400, srid=28992)
        point1 = WGS84.apply_to(rd_point, clone=True, axis_order=AxisOrder.TRADITIONAL)
        assert point1.x == pytest.approx(4.893, rel=0.001)
        assert point1.y == pytest.approx(52.373, rel=0.001)

        point2 = WGS84.apply_to(rd_point, clone=True, axis_order=AxisOrder.AUTHORITY)
        assert point1.x == point2.y
        assert point1.y == point2.x

    def test_axis_order_keep_traditional(self):
        """Prove that keeping traditional axis ordering works."""
        db_point = Point(4.8936582, 52.3731716, srid=WGS84.srid)  # in storage ordering.
        wgs84_point = WGS84.apply_to(db_point, clone=True, axis_order=AxisOrder.TRADITIONAL)
        assert db_point == wgs84_point

    def test_axis_order_wgs84_changes(self):
        # In CRS ordering in storage, yet converted to y/x in applications
        db_point = Point(4.8936582, 52.3731716, srid=WGS84.srid)  # in storage ordering.

        wgs84_point = WGS84.apply_to(db_point, clone=True)
        assert wgs84_point.y == db_point.x
        assert wgs84_point.x == db_point.y

        # Prove that applying again has no effect of flipping again.
        wgs84_point2 = WGS84.apply_to(wgs84_point, clone=True)
        assert wgs84_point == wgs84_point2

    def test_axis_order_crs(self, settings):
        rd_point = Point(121400, 487400, srid=28992)

        # https://epsg.io/4326
        wgs84 = CRS.from_string("urn:ogc:def:crs:EPSG::4326")
        assert wgs84.is_north_east_order
        wgs84_point = wgs84.apply_to(rd_point, clone=True)
        assert round(wgs84_point.x, 6) == 52.373446  # 52 first
        assert round(wgs84_point.y, 6) == 4.893804

        # For CRS84 its always longitude/latitude, which GeoJSON uses
        crs84 = CRS.from_string("urn:ogc:def:crs:OGC::CRS84")
        assert not crs84.is_north_east_order
        crs84_point = crs84.apply_to(rd_point, clone=True)
        assert round(crs84_point.x, 6) == 4.893804  # 4 first
        assert round(crs84_point.y, 6) == 52.373446

    @pytest.mark.parametrize("force_xy", [False, True], ids=["modern", "force_xy"])
    def test_axis_order_legacy(self, settings, force_xy):
        """Prove that legacy ordering is applied when a legacy notation is used."""
        settings.GISSERVER_FORCE_XY_EPSG_4326 = force_xy

        rd_point = Point(121400, 487400, srid=28992)

        # Legacy intput, legacy conversion
        wgs84_point = CRS.from_string("EPSG:4326").apply_to(rd_point, clone=True)

        if force_xy:
            assert round(wgs84_point.x, 6) == 4.893804
            assert round(wgs84_point.y, 6) == 52.373446
        else:
            assert round(wgs84_point.x, 6) == 52.373446
            assert round(wgs84_point.y, 6) == 4.893804

    def test_axis_order_finland(self):
        wgs84_point = Point(19.08, 58.84, srid=WGS84.srid)  # in PostGIS storage ordering
        finland_crs = CRS.from_string("urn:ogc:def:crs:EPSG::3879")  # https://epsg.io/3879
        finland_point = finland_crs.apply_to(wgs84_point, clone=True)
        assert round(int(finland_point.x), -2) == 6540000  # 65... first
        assert round(int(finland_point.y), -2) == 25158500

    def test_wgs_to_rd(self):
        wgs84_point = Point(4.8936582, 52.3731716, srid=WGS84.srid)  # in storage ordering.
        netherlands_crs = CRS.from_string("urn:ogc:def:crs:EPSG::28992")  # https://epsg.io/28992
        rd_point = netherlands_crs.apply_to(wgs84_point, clone=True)
        assert round(int(rd_point.x), -2) == 121400  # 12... first
        assert round(int(rd_point.y), -2) == 487400

    def test_coordinates(self, coordinates):
        # confirm it renders as x/y
        assert coordinates.point1_geojson[0] == pytest.approx(4.908, rel=0.001)
        assert coordinates.point1_geojson[1] == pytest.approx(52.363, rel=0.001)

        assert coordinates.point2_geojson[0] == pytest.approx(6.02, rel=0.001)
        assert coordinates.point2_geojson[1] == pytest.approx(50.75, rel=0.001)

        assert coordinates.point1_xml_wgs84.startswith("52.363")
        assert coordinates.point1_xml_wgs84_bbox.startswith("4.908")
