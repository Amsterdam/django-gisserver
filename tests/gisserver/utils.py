from doctest import Example
from functools import lru_cache
from pathlib import Path
from typing import Union

from lxml import etree
from lxml.doctestcompare import PARSE_XML, LXMLOutputChecker

# XSD schemas are downloaded from http://schemas.opengis.net/wfs/2.0/wfs.xsd
# using https://github.com/n-a-t-e/xsd_download/blob/master/xsd_download.py
# The download itself is really slow, hence these files are cached.
XSD_ROOT = Path(__file__).parent.parent.joinpath("files/xsd")
WFS_20_XSD = XSD_ROOT.joinpath("schemas.opengis.net/wfs/2.0/wfs.xsd")


@lru_cache(maxsize=100)
def compile_xsd(xsd_file) -> etree.XMLSchema:
    """Compile the XSD files into an lxml """
    xmlschema_doc = etree.parse(str(xsd_file))
    return etree.XMLSchema(xmlschema_doc)


def validate_xsd(xml_text: bytes, xsd_file: str) -> etree._Element:
    """Validate an XML file"""
    xml_schema = compile_xsd(xsd_file)

    xml_doc = etree.fromstring(xml_text)
    if not xml_schema.validate(xml_doc):
        # Improve error message display, to ease debugging of XML data
        source_lines = xml_text.decode().splitlines()
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


def assert_xml_equal(got: Union[bytes, str], want: str):
    """Compare two XML strings."""
    checker = LXMLOutputChecker()
    if not checker.check_output(want, got, PARSE_XML):
        example = Example("", "")
        example.want = want  # unencoded, avoid doctest for bytes type.
        message = checker.output_difference(example, got, PARSE_XML)
        raise AssertionError(message)
