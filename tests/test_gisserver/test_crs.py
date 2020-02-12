from gisserver.types import CRS, WGS84


class TestCRS:
    def test_from_string(self):
        assert CRS.from_string(4326).urn == "urn:ogc:def:crs:EPSG::4326"
        assert CRS.from_string("EPSG:4326").urn == "urn:ogc:def:crs:EPSG::4326"

    def test_crs84_inequal(self):
        """Prove that using strings from other vendors is also parsed.
        """
        crs84 = CRS.from_string("urn:ogc:def:crs:OGC:1.3:CRS84")
        assert crs84.srid == WGS84.srid

        # EPSG:4326 specifies coordinates in lat/long order and CRS:84 in long/lat order
        assert crs84 != WGS84

    def test_crs_empty_version(self):
        """Prove that empty versions are properly re-encoded as empty string"""
        assert (
            CRS.from_string("urn:ogc:def:crs:EPSG::28992").urn
            == "urn:ogc:def:crs:EPSG::28992"
        )
