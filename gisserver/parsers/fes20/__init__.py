from typing import Union

from defusedxml.ElementTree import fromstring

from .filters import Filter


def parse_fes(text: Union[str, bytes]) -> Filter:
    """Parse an XML <fes20:Filter> string.

    This uses defusedxml by default, to avoid various XML injection attacks.
    """
    root_element = fromstring(text)
    return Filter.from_xml(root_element)
