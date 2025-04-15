from typing import Dict, Optional
from collections.abc import Callable
from importlib.metadata import entry_points, Distribution, PackageNotFoundError
from importlib import reload
import sys
from .._logging import FUNCNODES_LOGGER
from .plugins_types import InstalledModule, BasePlugin  # noqa: F401


def reload_plugin_module(module_name: str):
    """
    Reload a module by its name.

    Args:
      module_name (str): The name of the module to reload.

    Returns:
      None
    """
    if module_name in sys.modules:
        try:
            reload(sys.modules[module_name])
        except Exception as e:
            FUNCNODES_LOGGER.exception(f"Failed to reload {module_name}: {e}")
    else:
        # import the module to ensure it is loaded
        try:
            __import__(module_name)
        except ImportError as e:
            FUNCNODES_LOGGER.exception(f"Failed to import {module_name}: {e}")
            raise ImportError(f"Module {module_name} not found") from e

    modulde_data = InstalledModule(
        name=module_name,
        entry_points={},
        module=None,  # module not directly added since only modules with a module entry point are relevant
    )

    modulde_data = assert_entry_points_loaded(modulde_data)
    modulde_data = assert_module_metadata(modulde_data)

    return modulde_data


def assert_entry_points_loaded(modulde_data: InstalledModule):
    for ep in entry_points(group="funcnodes.module", module=modulde_data.name):
        if ep.name in modulde_data.entry_points:
            continue
        try:
            loaded = ep.load()
            modulde_data.entry_points[ep.name] = loaded
            if ep.name == "module":
                modulde_data.module = loaded
        except Exception as exc:
            FUNCNODES_LOGGER.exception(f"Failed to load entry point {ep.name}: {exc}")

    return modulde_data


def assert_module_metadata(modulde_data: InstalledModule):
    def lazydist() -> Callable[[], Distribution]:
        _DIST = None

        def _lazydist() -> Distribution:
            nonlocal _DIST
            if _DIST is not None:
                return _DIST
            dist = None
            try:
                dist = Distribution.from_name(modulde_data.name)
            except PackageNotFoundError as exc:
                for ep in entry_points(
                    group="funcnodes.module", module=modulde_data.name
                ):
                    try:
                        if ep.dist:
                            dist = ep.dist
                            break
                    except PackageNotFoundError:
                        pass

                if dist is None:
                    raise exc
            _DIST = dist

        return _lazydist

    # use lasydist to avoid loading the distribution multiple times and only when needed
    dist = lazydist()

    if not modulde_data.description:
        try:
            package_metadata = dist().metadata
            description = package_metadata.get("Summary", "No description available")
        except Exception as e:
            description = f"Could not retrieve description: {str(e)}"
        modulde_data.description = description

    if not modulde_data.version:
        try:
            modulde_data.version = dist().version
        except Exception:
            pass

    return modulde_data


def get_installed_modules(
    named_objects: Optional[Dict[str, InstalledModule]] = None,
) -> Dict[str, InstalledModule]:
    if named_objects is None:
        named_objects: Dict[str, InstalledModule] = {}

    modules = set()

    for ep in entry_points(group="funcnodes.module"):
        module_name = ep.module
        modules.add(module_name)
    for module_name in modules:
        if module_name not in named_objects:
            named_objects[module_name] = reload_plugin_module(module_name)
        modulde_data = named_objects[module_name]
        modulde_data = assert_entry_points_loaded(modulde_data)
        modulde_data = assert_module_metadata(modulde_data)

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
