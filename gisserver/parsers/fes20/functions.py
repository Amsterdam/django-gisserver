"""Functions to be callable from fes."""

__all__ = ["function_registry"]


class FesFunctionRegistry:
    """Registry of functions to be callable by <fes:Function>.

    The registered functions should be capable of running an SQL function.
    """

    def __init__(self):
        self.functions = {}

    def register(self, name=None):
        def _wrapper(callable):
            self.functions[name or callable.__name__] = callable
            return callable

        return _wrapper


function_registry = FesFunctionRegistry()


@function_registry.register("min")
def fes_min(value1: float, value2: float) -> float:
    """Wrapper for min() with the proper fes arguments and types."""
    return min(value1, value2)


@function_registry.register("max")
def fes_max(value1: float, value2: float) -> float:
    """Wrapper for max() with the proper fes arguments and types."""
    return max(value1, value2)
