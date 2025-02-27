from typing import Dict
from collections.abc import Callable
from importlib.metadata import entry_points
from importlib import reload
import sys
from .._logging import FUNCNODES_LOGGER
from .plugins_types import InstalledModule, BasePlugin  # noqa: F401


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


PLUGIN_FUNCTIONS: Dict[str, Callable[[InstalledModule], None]] = {}


def register_setup_plugin(plugin_function: Callable[[InstalledModule], None]):
    """
    Register a function to be called when a module is loaded.

    Args:
      plugin_function (Callable[[InstalledModule],None]): The function to call when a module is loaded.

    Returns:
      None
    """
    module = plugin_function.__module__

    PLUGIN_FUNCTIONS[module] = plugin_function
