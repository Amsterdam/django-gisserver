"""Functions to be callable from fes."""
from typing import Callable, Dict, Optional, Union

from django.db import models
from django.db.models.expressions import Combinable

from gisserver.exceptions import InvalidParameterValue

__all__ = ["function_registry"]

FesArg = Union[Combinable, models.Q]
FesFunction = Callable[..., models.Func]


class FesFunctionRegistry:
    """Registry of functions to be callable by <fes:Function>.

    The registered functions should be capable of running an SQL function.
    """

    def __init__(self):
        self.functions = {}

    def register(
        self,
        name=None,
        *,
        arguments: Optional[Dict[str, str]] = None,
        returns: Optional[str] = None,
    ):
        """Decorator to register a function.

        It's not recommended to register the Django Func objects directly,
        as the parameters are passed on from the client-side. Instead, create
        a wrapper function that enforces a controlled set of parameters.
        """

        def _wrapper(callable: FesFunction):
            self.functions[name or callable.__name__] = callable
            callable._fes_arguments = arguments
            callable._fes_returns = returns
            return callable

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


@function_registry.register(
    "min",
    arguments=dict(value1="xsd:double", value2="xsd:double"),
    returns="xsd:double",
)
def fes_min(value1, value2) -> models.Func:
    """Wrapper for SQL Min() with the proper fes arguments and types."""
    return models.Min(value1, value2)


@function_registry.register(
    "max",
    arguments=dict(value1="xsd:double", value2="xsd:double"),
    returns="xsd:double",
)
def fes_max(value1, value2) -> models.Func:
    """Wrapper for SQL Max() with the proper fes arguments and types."""
    return models.Max(value1, value2)
