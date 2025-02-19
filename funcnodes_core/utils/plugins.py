from typing import Dict

from importlib.metadata import entry_points
from importlib import reload
import sys
from .._logging import FUNCNODES_LOGGER
from .plugins_types import InstalledModule


def resolve(dotted_name: str):
    """
    Resolve a fully qualified (dotted) name to a global Python object.

    This function takes a string representing a fully qualified name of an object,
    such as a module, class, function, or attribute (e.g., 'os.path.join' or
    'package.module.ClassName'), and returns the corresponding object. It does this
    by:

      1. Splitting the dotted name into its component parts.
      2. Importing the base module.
      3. Iteratively retrieving each attribute specified in the remaining parts.
         If an attribute is not found, it attempts to import the module corresponding
         to the current dotted path and then retries the attribute lookup.

    Parameters:
        dotted_name (str): The fully qualified name of the target object.

    Returns:
        object: The Python object corresponding to the given dotted name.

    Raises:
        ImportError: If the initial module or any subsequent module cannot be imported.
        AttributeError: If an attribute does not exist in the module after import.
    """
    parts = dotted_name.split(".")
    module_name = parts.pop(0)
    current_object = __import__(module_name)
    for part in parts:
        module_name = f"{module_name}.{part}"
        try:
            current_object = getattr(current_object, part)
        except AttributeError:
            __import__(module_name)
            current_object = getattr(current_object, part)
    return current_object


def get_installed_modules() -> Dict[str, InstalledModule]:
    named_objects: Dict[str, InstalledModule] = {}

    for ep in entry_points(group="funcnodes.module"):
        try:
            if ep.value in sys.modules:
                loaded = reload(sys.modules[ep.value])
            else:
                loaded = ep.load()
            module_name = ep.module

            if module_name not in named_objects:
                named_objects[module_name] = InstalledModule(
                    name=module_name,
                    entry_points={},
                    module=None,
                )

            named_objects[module_name].entry_points[ep.name] = loaded
            if ep.name == "module":
                named_objects[module_name].module = loaded

            # Populate version and description if not already set
            if not named_objects[module_name].description:
                try:
                    package_metadata = ep.dist.metadata
                    description = package_metadata.get(
                        "Summary", "No description available"
                    )
                except Exception as e:
                    description = f"Could not retrieve description: {str(e)}"
                named_objects[module_name].description = description

            if not named_objects[module_name].version:
                try:
                    named_objects[module_name].version = ep.dist.version
                except Exception:
                    pass
        except AttributeError:
            raise
        except Exception as exc:
            FUNCNODES_LOGGER.exception(exc)

    return named_objects
