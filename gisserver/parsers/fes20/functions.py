"""Functions to be callable from fes."""
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Union

from django.db import models
from django.db.models import functions
from django.contrib.gis.db.models import functions as gis
from django.db.models.expressions import Combinable

from gisserver.exceptions import InvalidParameterValue
from gisserver.types import XsdTypes

__all__ = ["function_registry"]

FesArg = Union[Combinable, models.Q]
FesFunctionBody = Union[models.Func, Callable[..., models.Func]]


@dataclass(order=True)
class FesFunction:
    """Wrapper that defines a fes function, with type descriptions.
    This is also used to provide metadata to the GetCapabilities call.
    """

    #: Name of the function
    name: str

    #: The function body
    body: FesFunctionBody

    #: The argument names with their XSD types
    arguments: Optional[Dict[str, XsdTypes]] = None

    #: The XSD return type
    returns: Optional[XsdTypes] = None

    def build_query(self, *expressions: FesArg) -> models.Func:
        """Build the query expression for the function."""
        if len(expressions) != len(self.arguments):
            # Avoid passing extra parameters to the function if those are not defined.
            raise TypeError(
                f'Invalid number of arguments for <fes:Function name="{self.name}">'
            )

        # Keyword arguments are avoided, since some Django SQL functions had
        # SQL-injection issues with those arguments. Only passing expressions for now.
        return self.body(*expressions)


class FesFunctionRegistry:
    """Registry of functions to be callable by <fes:Function>.

    The registered functions should be capable of running an SQL function.
    """

    def __init__(self):
        self.functions = {}

    def __bool__(self):
        return bool(self.functions)

    def __iter__(self):
        return iter(sorted(self.functions.values()))  # for template rendering

    def register(
        self,
        name=None,
        body: Optional[FesFunctionBody] = None,
        *,
        arguments: Optional[Dict[str, XsdTypes]] = None,
        returns: Optional[XsdTypes] = None,
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
        """Resole the function using it's name."""
        try:
            return self.functions[function_name]
        except KeyError:
            raise InvalidParameterValue(
                "filter", f"Unsupported function: {function_name}"
            ) from None


function_registry = FesFunctionRegistry()


# Register a set of default SQL functions.
# These are based on GeoServer:
# https://docs.geoserver.org/latest/en/user/filter/function_reference.html
# Not implemented:
# - Aggregates (like Collection_*)
# - Comparisons (which already has fes variants)

# -- strings

function_registry.register(
    "strConcat",
    functions.Concat,
    arguments={"string1": XsdTypes.string, "string2": XsdTypes.string},
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
    arguments={"base": XsdTypes.double},
    returns=XsdTypes.integer,
)

function_registry.register(
    "exp", functions.Exp, arguments={"value": XsdTypes.double}, returns=XsdTypes.double,
)

function_registry.register(
    "log", functions.Log, arguments={"value": XsdTypes.double}, returns=XsdTypes.double,
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
    "pi", functions.Pi, returns=XsdTypes.double,
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
    "Area",
    gis.Area,
    arguments={"geometry": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.double,
)

function_registry.register(
    "Centroid",
    gis.Centroid,
    arguments={"features": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.string,
)

function_registry.register(
    "Difference",
    gis.Difference,
    arguments={
        "geometry1": XsdTypes.gmlAbstractGeometryType,
        "geometry2": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.string,
)

function_registry.register(
    "distance",
    gis.Distance,
    arguments={
        "geometry1": XsdTypes.gmlAbstractGeometryType,
        "geometry2": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.double,
)

function_registry.register(
    "Envelope",
    gis.Envelope,
    arguments={"geometry": XsdTypes.gmlAbstractGeometryType},
    returns=XsdTypes.string,
)

function_registry.register(
    "Intersection",
    gis.Intersection,
    arguments={
        "geometry1": XsdTypes.gmlAbstractGeometryType,
        "geometry2": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.string,
)

function_registry.register(
    "Union",
    gis.Union,
    arguments={
        "geometry1": XsdTypes.gmlAbstractGeometryType,
        "geometry2": XsdTypes.gmlAbstractGeometryType,
    },
    returns=XsdTypes.string,
)
