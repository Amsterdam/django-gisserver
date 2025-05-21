"""Parsing the Key-Value-Pair (KVP) request format."""

from __future__ import annotations

from copy import copy

from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OperationParsingFailed,
    wrap_parser_errors,
)
from gisserver.parsers.xml import parse_qname, xmlns

REQUIRED = ...  # sentinel value


class KVPRequest:
    """The Key-Value-Pair (KVP) request format.

    This handles parameters from the HTTP GET request.
    It includes notation format support for certain parameters,
    such as comma-separated lists, and parenthesis-grouping notations.

    Some basic validation is performed, allowing to convert the data into Python types.
    """

    def __init__(self, query_string: dict[str, str], ns_aliases: dict[str, str] | None = None):
        # The parameters are case-insensitive.
        self.params = {name.upper(): value for name, value in query_string.items()}

        # Make sure most common namespaces are known for resolving them.
        self.ns_aliases = {
            **xmlns.as_ns_aliases(),  # some defaults in case these are missing in the request
            **(ns_aliases or {}),  # our local application namespaces
            **parse_kvp_namespaces(self.params.get("NAMESPACES")),  # extra in the request
        }

    def __contains__(self, name: str) -> bool:
        """Tell whether a parameter is present."""
        return name.upper() in self.params

    def get_custom(self, name: str, *, alias: str | None = None, default=REQUIRED, parser=None):
        """Retrieve a value by name.
        This performs basic validation, similar to what the XML parsing does.

        Any parsing errors or validation checks are raised as WFS Exceptions,
        meaning the client will get the appropriate response.

        :param name: The name of the parameter, typically given in its XML notation format (camelCase).
        :param alias: An older WFS 1 to try for compatibility (e.g. TYPENAMES/TYPENAME, COUNT/MAXFEATURES)
        :param default: The default value to return. If not provided, the parameter is required.
        :param parser: A custom Python function or type to convert the value with.
        """
        kvp_name = name.upper()
        value = self.params.get(kvp_name)
        if not value and alias:
            value = self.params.get(alias.upper())

        # Check required field settings, both empty and missing value are treated the same.
        if not value:
            if default is REQUIRED:
                if value is None:
                    raise MissingParameterValue(
                        f"Missing required '{name}' parameter.", locator=name
                    )
                else:
                    raise InvalidParameterValue(f"Empty '{kvp_name}' parameter", locator=name)
            return default

        # Allow conversion into a python object
        if parser is not None:
            with wrap_parser_errors(kvp_name, locator=name):
                return parser(value)
        else:
            return value

    def get_str(
        self, name: str, *, alias: str | None = None, default: str | None = REQUIRED
    ) -> str | None:
        """Retrieve a string value from the request."""
        return self.get_custom(name, alias=alias, default=default)

    def get_int(
        self, name: str, *, alias: str | None = None, default: int | None = REQUIRED
    ) -> int | None:
        """Retrieve an integer value from the request."""
        return self.get_custom(name, alias=alias, default=default, parser=int)

    def get_list(
        self, name, *, alias: str | None = None, default: list | None = REQUIRED
    ) -> list[str] | None:
        """Retrieve a comma-separated list value from the request."""
        return self.get_custom(
            name,
            alias=alias,
            default=default,
            parser=lambda x: x.split(","),
        )

    def parse_qname(self, value) -> str:
        """Convert the value to an XML fully qualified name."""
        return parse_qname(value, self.ns_aliases)

    def split_parameter_lists(self) -> list[KVPRequest]:
        """Split the parameter lists into individual requests.

        This translates a request such as:

        .. code-block:: urlencoded

            TYPENAMES=(ns1:F1,ns2:F2)(ns1:F1,ns1:F1)
            &ALIASES=(A,B)(C,D)
            &FILTER=(<Filter>… for A,B …</Filter>)(<Filter>…for C,D…</Filter>)

        into separate pairs:

        .. code-block:: urlencoded

            TYPENAMES=ns1:F1,ns2:F2&ALIASES=A,B&FILTER=<Filter>…for A,B…</Filter>
            TYPENAMES=ns1:F1,ns1:F1&ALIASES=C,D&FILTER=<Filter>…for C,D…</Filter>

        It's both possible have some query parameters split and some shared.
        For example to have two different bounding boxes:

        .. code-block:: urlencoded

             TYPENAMES=(INWATER_1M)(BuiltUpA_1M)&BBOX=(40.9821,...)(40.5874,...)

        or have a single bounding box for both queries:

        .. code-block:: urlencoded

             TYPENAMES=(INWATER_1M)(BuiltUpA_1M)&BBOX=40.9821,23.4948,41.0257,23.5525
        """
        pairs = {
            name: value[1:-1].split(")(")
            for name, value in self.params.items()
            if value.startswith("(") and value.endswith(")")
        }
        if not pairs:
            return [self]

        pair_sizes = {len(value) for value in pairs.values()}
        if len(pair_sizes) > 1:
            keys = sorted(pairs)
            raise OperationParsingFailed(
                f"Inconsistent pairs between: {', '.join(keys)}", locator=keys[0]
            )

        # Produce variations of the same request object
        pair_size = next(iter(pair_sizes))
        variants = []
        for i in range(pair_size):
            updates = {key: value[i] for key, value in pairs.items()}
            variant = copy(self)
            variant.params = {**self.params, **updates}
            variants.append(variant)
        return variants


def parse_kvp_namespaces(value) -> dict[str, str]:
    """Parse the 'NAMESPACES' parameter format to lookups.

    The NAMESPACES parameter defines which namespaces are used in the KVP request.
    When this parameter is not given, the default namespaces are assumed.
    """
    if not value:
        return {}

    # example single value: xmlns(http://example.org)
    # or: NAMESPACES=xmlns(xml,http://www.w3.org/...),xmlns(wfs,http://www.opengis.net/...)
    tokens = value.split(",")

    namespaces = {}
    tokens = iter(tokens)
    for prefix in tokens:
        if not prefix.startswith("xmlns("):
            raise InvalidParameterValue(
                f"Expected xmlns(...) format: {value}", locator="namespaces"
            )
        if prefix.endswith(")"):
            # xmlns(http://...)
            uri = prefix[6:-1]
            prefix = ""
        else:
            uri = next(tokens, "")
            if not uri.endswith(")"):
                raise InvalidParameterValue(
                    f"Expected xmlns(prefix,uri) format: {value}",
                    locator="namespaces",
                )
            prefix = prefix[6:]
            uri = uri[:-1]

        namespaces[prefix] = uri

    return namespaces
