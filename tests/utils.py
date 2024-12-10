from __future__ import annotations

import re
from doctest import Example
from functools import lru_cache
from pathlib import Path

import orjson
from django.http.response import HttpResponseBase
from lxml import etree
from lxml.doctestcompare import PARSE_XML, LXMLOutputChecker

# XSD schemas are downloaded from http://schemas.opengis.net/wfs/2.0/wfs.xsd
# using https://github.com/n-a-t-e/xsd_download/blob/master/xsd_download.py
# The download itself is really slow, hence these files are cached.
XSD_ROOT = Path(__file__).parent.joinpath("files/xsd")
GML321_XSD = str(XSD_ROOT.joinpath("schemas.opengis.net/gml/3.2.1/gml.xsd"))
WFS_20_XSD = str(XSD_ROOT.joinpath("schemas.opengis.net/wfs/2.0/wfs.xsd"))


def read_response(response: HttpResponseBase) -> str:
    # works for all HttpResponse subclasses.
    return b"".join(response).decode()


def read_json(content) -> dict:
    try:
        return orjson.loads(content)
    except orjson.JSONDecodeError as e:
        snippet = content[e.pos - 300 : e.pos + 300]
        snippet = snippet[snippet.index("\n") :]  # from last newline
        raise AssertionError(f"Parsing JSON failed: {e}\nNear: {snippet}") from None


def get_sql(captured_queries: list[dict]) -> list[str]:
    """Extract the SQL statements made during execution."""
    return [
        re.sub(
            r'^DECLARE "_django_curs_\d+_sync_\d+" NO SCROLL CURSOR WITHOUT HOLD FOR ',
            "",
            q["sql"],
        )
        for q in captured_queries
    ]


@lru_cache(maxsize=100)
def compile_xsd(xsd_file, xsd_content=None) -> etree.XMLSchema:
    """Compile the XSD files into a lxml tree"""
    if xsd_file:
        if xsd_file[0] == "<":
            raise TypeError("XML passed to xsd_file parameter")
        return etree.XMLSchema(file=xsd_file)
    elif xsd_content:
        # Make sure the whole WFS XSD doesn't need to be downloaded (really slow, 24 files)
        xsd_content = xsd_content.replace(
            "http://schemas.opengis.net", str(XSD_ROOT.joinpath("schemas.opengis.net"))
        )
        return etree.XMLSchema(etree=etree.fromstring(xsd_content.encode()))
    else:
        raise TypeError("pass xsd_file or xsd_content)")


def validate_xsd(xml_text: bytes | str, xsd_file=None, xsd_content=None) -> etree._Element:
    """Validate an XML file"""
    xml_schema = compile_xsd(xsd_file=xsd_file, xsd_content=xsd_content)

    if isinstance(xml_text, str):
        xml_str = xml_text
        xml_bytes = xml_text.encode()
    else:
        xml_bytes = xml_text
        xml_str = xml_text.decode()

    try:
        xml_doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as err:
        source_lines = xml_str.splitlines()
        raise etree.DocumentInvalid(
            f"{err.text} at {err.lineno}:{err.offset + 1} "
            f"in {err.filename} (source: {source_lines[err.lineno - 1].strip()})"
        ) from err

    if not xml_schema.validate(xml_doc):
        # Improve error message display, to ease debugging of XML data
        source_lines = xml_str.splitlines()
        raise etree.DocumentInvalid(
            "\n".join(
                [
                    f"{err.message} at {err.line}:{err.column} "
                    f"in {err.path} (source: {source_lines[err.line - 1].strip()})"
                    for err in xml_schema.error_log
                ]
            )
        )

    return xml_doc


def assert_xml_equal(got: bytes | str, want: str):
    """Compare two XML strings."""
    checker = LXMLOutputChecker()

    if isinstance(want, str) and isinstance(got, bytes):
        got = got.decode()

    if isinstance(got, str) and got.startswith("<?"):
        # Strip <?xml version='1.0' encoding="UTF-8" ?>
        # because it's not supported on utf-8 strings
        got = got[got.index("?>") + 3 :]

    if not checker.check_output(want, got, PARSE_XML):
        example = Example("", "")
        example.want = want  # unencoded, avoid doctest for bytes type.
        message = checker.output_difference(example, got, PARSE_XML)
        raise AssertionError(message)
