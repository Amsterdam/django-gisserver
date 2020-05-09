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
GML321_XSD = str(XSD_ROOT.joinpath("schemas.opengis.net/gml/3.2.1/gml.xsd"))
WFS_20_XSD = str(XSD_ROOT.joinpath("schemas.opengis.net/wfs/2.0/wfs.xsd"))


@lru_cache(maxsize=100)
def compile_xsd(xsd_file, xsd_content=None) -> etree.XMLSchema:
    """Compile the XSD files into an lxml """
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


def validate_xsd(
    xml_text: Union[bytes, str], xsd_file=None, xsd_content=None
) -> etree._Element:
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


def assert_xml_equal(got: Union[bytes, str], want: str):
    """Compare two XML strings."""
    checker = LXMLOutputChecker()
    if isinstance(got, str):
        got = got.encode()

    if not checker.check_output(want, got, PARSE_XML):
        example = Example("", "")
        example.want = want  # unencoded, avoid doctest for bytes type.
        message = checker.output_difference(example, got, PARSE_XML)
        raise AssertionError(message)
