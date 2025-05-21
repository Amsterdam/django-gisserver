"""Functions to be callable from query filters.

By using the :attr:`function_registry`, custom stored functions can be registered in this server.
These are called by the filter queries using the :class:`~gisserver.parsers.fes20.expressions.Function` element.
Out of the box, various built-in functions are present.

Built-in options are documented in :ref:`functions`.

Most of the out-of-the box options are inspired
by `GeoServer <https://docs.geoserver.org/latest/en/user/filter/function_reference.html>`_.
Functions which already have a fes-syntax equivalent have been are omitted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Union

import django
from django.contrib.gis.db.models import functions as gis
from django.db import models
from django.db.models import functions
from django.db.models.expressions import Combinable, Value

from gisserver.exceptions import InvalidParameterValue
from gisserver.types import XsdTypes

__all__ = ["function_registry", "FesFunctionRegistry", "FesFunction"]

FesArg = Union[Combinable, models.Q]
FesFunctionBody = Union[models.Func, Callable[..., models.Func]]


@dataclass(order=True)
class FesFunction:
    """A registered database function that can be used by ``<fes:Function name="...">``.

    The :class:`~gisserver.parsers.fes20.expressions.Function` class will resolve
    these registered functions by name, and call :meth:`build_query` to include them
    in the database query. This will actually insert a Django ORM function in the query!

    This wrapper class also provides the metadata and type descriptions of the function,
    which is exposed in the ``GetCapabilities`` call.
    """

    #: Name of the function
    name: str

    #: The function body
    body: FesFunctionBody

    #: The argument names with their XSD types
    arguments: dict[str, XsdTypes] | None = None

    #: The XSD return type
    returns: XsdTypes | None = None

    def build_query(self, *expressions: FesArg) -> models.Func:
        """Build the query expression for the function."""
        if len(expressions) != len(self.arguments):
            # Avoid passing extra parameters to the function if those are not defined.
            raise TypeError(f'Invalid number of arguments for <fes:Function name="{self.name}">')

        # Keyword arguments are avoided, since some Django SQL functions had
        # SQL-injection issues with those arguments. Only passing expressions for now.
        return self.body(*expressions)


class FesFunctionRegistry:
    """Registry of functions to be callable by ``<fes:Function>``.

    The registered functions should be capable of running an SQL function.
    """

    def __init__(self):
        self.functions = {}

    def __bool__(self):
        """Tell whether there are functions"""
        return bool(self.functions)

    def __iter__(self):
        """Iterate over the functions"""
        return iter(sorted(self.functions.values()))  # for template rendering

    def register(
        self,
        name=None,
        body: FesFunctionBody | None = None,
        *,
        arguments: dict[str, XsdTypes] | None = None,
        returns: XsdTypes | None = None,
    ):
        """Decorator to register a function.

        It's not recommended to register the Django Func objects directly,
        as the parameters are passed on from the client-side. Instead, create
        a wrapper function that enforces a controlled set of parameters.
        """

        def _wrapper(callable: FesFunctionBody):
            function = FesFunction(
                name=name or callable.__name__,
                body=callable,
                arguments=arguments,
                returns=returns,
            )
            self.functions[function.name] = function
            return callable

        if body is not None:
            # Usage as direct registration
            return _wrapper(body)
        else:
            # Usage as decorator
            return _wrapper

    def resolve_function(self, function_name) -> FesFunction:
        """Resole the function using its name."""
        try:
            return self.functions[function_name]
        except KeyError:
            raise InvalidParameterValue(
                f"Unsupported function: {function_name}", locator="filter"
            ) from None


#: The function registry
function_registry = FesFunctionRegistry()


# Register a set of default SQL functions.

# -- strings

function_registry.register(
    "strConcat",
    functions.Concat,
    arguments={"string1": XsdTypes.string, "string2": XsdTypes.string},
    returns=XsdTypes.string,
)

function_registry.register(
    "strIndexOf",
    lambda string, substring: (functions.StrIndex(string, Value(substring)) - 1),
    arguments={"string": XsdTypes.string, "substring": XsdTypes.string},
    returns=XsdTypes.string,
)

function_registry.register(
    "strSubstring",
    lambda string, begin, end: functions.Substr(string, begin + 1, end - begin),
    arguments={"string": XsdTypes.string, "begin": XsdTypes.integer, "end": XsdTypes.integer},
    returns=XsdTypes.string,
)

function_registry.register(
    "strSubstringStart",
    lambda string, begin, end: functions.Substr(string, begin + 1),
    arguments={"string": XsdTypes.string, "begin": XsdTypes.integer},
    returns=XsdTypes.string,
)

function_registry.register(
    "strToLowerCase",
    functions.Lower,
    arguments={"string": XsdTypes.string},
    returns=XsdTypes.string,
)

function_registry.register(
    "strToUpperCase",
    functions.Upper,
    arguments={"string": XsdTypes.string},
    returns=XsdTypes.string,
)

function_registry.register(
    "strTrim",
    functions.Trim,
    arguments={"string": XsdTypes.string},
    returns=XsdTypes.string,
)

function_registry.register(
    "strLength",
    functions.Length,
    arguments={"string": XsdTypes.string},
    returns=XsdTypes.integer,
)

function_registry.register(
    "length",
    functions.Length,
    arguments={"string": XsdTypes.string},
    returns=XsdTypes.integer,
)

# -- math numbers

function_registry.register(
    "abs",
    functions.Abs,
    arguments={"number": XsdTypes.decimal},
    returns=XsdTypes.double,
)

function_registry.register(
    "ceil",
    functions.Ceil,
    arguments={"number": XsdTypes.decimal},
    returns=XsdTypes.decimal,
)

function_registry.register(
    "floor",
    functions.Floor,
    arguments={"number": XsdTypes.decimal},
    returns=XsdTypes.decimal,
)

function_registry.register(
    "min",
    functions.Least,
    arguments={"value1": XsdTypes.double, "value2": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "max",
    functions.Greatest,
    arguments={"value1": XsdTypes.double, "value2": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "pow",
    functions.Power,
    arguments={"base": XsdTypes.double, "exponent": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "round",
    functions.Round,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.integer,
)

function_registry.register(
    "exp",
    functions.Exp,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "log",
    functions.Log,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "sqrt",
    functions.Sqrt,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

# -- math trigonometry

function_registry.register(
    "acos",
    functions.ACos,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "asin",
    functions.ASin,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "atan",
    functions.ATan,
    arguments={"value": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "atan2",
    functions.ATan2,
    arguments={"x": XsdTypes.double, "y": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "cos",
    functions.Cos,
    arguments={"radians": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "sin",
    functions.Sin,
    arguments={"radians": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "tan",
    functions.Tan,
    arguments={"radians": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "pi",
    functions.Pi,
    returns=XsdTypes.double,
)

function_registry.register(
    "toDegrees",
    functions.Degrees,
    arguments={"radians": XsdTypes.double},
    returns=XsdTypes.double,
)

function_registry.register(
    "toRadians",
    functions.Radians,
    arguments={"degree": XsdTypes.double},
    returns=XsdTypes.double,
)

# -- geometric

function_registry.register(
    "area",
    gis.Area,
    arguments={"geom": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.double,
)

function_registry.register(
    "centroid",
    gis.Centroid,
    arguments={"geom": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.string,
)

function_registry.register(
    "difference",
    gis.Difference,
    arguments={
        "a": XsdTypes.gmlAbstractGeometryType,
        "b": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.string,
)

function_registry.register(
    "distance",
    gis.Distance,
    arguments={
        "a": XsdTypes.gmlAbstractGeometryType,
        "b": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.double,
)

function_registry.register(
    "envelope",
    gis.Envelope,
    arguments={"geom": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.gmlAbstractGeometryType,  # returns point or polygon
)

function_registry.register(
    "geomLength",
    gis.Length,
    arguments={"geometry": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.float,
)

function_registry.register(
    "intersection",
    gis.Intersection,
    arguments={
        "a": XsdTypes.gmlAbstractGeometryType,
        "b": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.gmlAbstractGeometryType,
)

if django.VERSION >= (4, 2):
    function_registry.register(
        "isEmpty",
        gis.IsEmpty,
        arguments={
            "geom": XsdTypes.gmlAbstractGeometryType,
        },
        returns=XsdTypes.boolean,
    )

function_registry.register(
    "isValid",
    gis.IsValid,
    arguments={
        "geom": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.boolean,
)

function_registry.register(
    "numGeometries",
    gis.NumGeometries,
    arguments={
        "collection": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.integer,
)

function_registry.register(
    "numPoints",
    gis.NumPoints,
    arguments={
        "collection": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.integer,
)

function_registry.register(
    "perimeter",
    gis.Perimeter,
    arguments={
        "geom": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.integer,
)

function_registry.register(
    "symDifference",
    gis.SymDifference,
    arguments={
        "a": XsdTypes.gmlAbstractGeometryType,
        "b": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.gmlAbstractGeometryType,
)

function_registry.register(
    "union",
    gis.Union,
    arguments={
        "a": XsdTypes.gmlAbstractGeometryType,
        "b": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.gmlAbstractGeometryType,
)
