"""
This util module manages deprecations and warnings.
"""

import sys
from types import ModuleType
from typing import Optional, Any, TypeVar
from collections.abc import Callable
import warnings
from functools import wraps


T = TypeVar("T")


class FuncNodesDeprecationWarning(DeprecationWarning):
    """A custom deprecation warning for FuncNodes, to distinguish from dependency warnings."""


class SpellingDeprecationWarning(DeprecationWarning):
    """A custom deprecation warning for spelling mistakes."""


def path_module_attribute_to_getter(
    module: ModuleType,  # The module object (or module name) to modify.
    attribute: str,  # The name of the deprecated attribute.
    true_getter: Callable[
        [], T
    ],  # The function to call instead of accessing the attribute directly.
    true_setter: Optional[
        Callable[[Any], Any]
    ],  # Optional function to call when setting the attribute.
) -> T:
    # Allow passing the module as a string (its name) or as the module object.
    if isinstance(module, str):
        module = sys.modules[module]

    # Define a getter that will be attached as a property.
    # When the deprecated attribute is accessed, this function is called.
    def _inplace_getter(self):
        # Issue a deprecation warning, indicating the recommended alternative.
        warnings.warn(
            f"Attribute {attribute} is deprecated. Use {true_getter.__name__}() instead.",
            FuncNodesDeprecationWarning,
            stacklevel=2,
        )
        # Return the value by calling the new (true) getter function.
        return true_getter()

    # Create a dictionary of attributes that will be added to a new type.
    # We start by adding our property for the deprecated attribute.
    attrs = {
        attribute: property(_inplace_getter),
    }

    # If a setter function is provided, add a setter to the property.
    if true_setter is not None:
        # Define a setter that will be used when someone assigns a value to the attribute.
        def _inplace_setter(self, value):
            # Issue a deprecation warning for setting the attribute.
            warnings.warn(
                f"Attribute {attribute} is deprecated. Use {true_setter.__name__}(value) instead.",
                FuncNodesDeprecationWarning,
                stacklevel=2,
            )
            # Delegate the setting to the true setter function.
            return true_setter(value)

    else:
        # If no setter is provided, use a default setter that raises an error.
        def _inplace_setter(self, value):
            raise AttributeError(f"Attribute {attribute} is read-only.")

    # Update the property to include the setter.
    attrs[attribute] = attrs[attribute].setter(_inplace_setter)

    # Create a new type (class) that will be used to replace the module's __class__.
    # This new class inherits from the module's original class and includes our new property.
    new_cls = type(
        module.__class__.__name__,  # Use the original class name.
        (module.__class__,),  # Inherit from the module's original class.
        attrs,  # Add the new attributes (property) to the class.
    )

    # Replace the module's __class__ with the new class.
    # This effectively "monkey-patches" the module so that accessing the deprecated attribute
    # goes through our property (which warns and delegates to the true getter/setter).
    module.__class__ = new_cls

    return true_getter()


def method_deprecated_decorator(alternative=None):
    def decorator(method):
        @wraps(method)
        def wrapper(*args, **kwargs):
            warntext = f"Method {method.__name__} is deprecated."
            if alternative:
                warntext += f" Use {alternative} instead."

            warnings.warn(
                warntext,
                FuncNodesDeprecationWarning,
                stacklevel=2,
            )
            return method(*args, **kwargs)

        return wrapper

    return decorator
