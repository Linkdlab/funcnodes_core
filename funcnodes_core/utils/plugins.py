from typing import Dict, Any, Optional, TypedDict
from dataclasses import dataclass, field

import pkg_resources

from importlib.metadata import metadata


try:
    from funcnodes_react_flow import ReactPlugin
except (ModuleNotFoundError, ImportError):
    ReactPlugin = dict


class RenderOptions(TypedDict, total=False):
    """
    A typed dictionary for render options.

    Attributes:
      typemap (dict[str, str]): A dictionary mapping types to strings.
      inputconverter (dict[str, str]): A dictionary mapping input types to strings.
    """

    typemap: dict[str, str]
    inputconverter: dict[str, str]


class LoadedModule(TypedDict):
    """
    TypedDict for an individual loaded module.

    Attributes:
        name (str): The name of the entry point.
        object (Any): The actual object loaded from the entry point.
    """

    name: str
    object: Any


@dataclass
class InstalledModule:
    """
    TypedDict for an installed module.

    Attributes:
        description (str): The description of the module.
        entry_points (Dict[str, LoadedModule]): Dictionary of entry points for the module.
    """

    name: str
    module: Any
    description: Optional[str] = None
    entry_points: Dict[str, LoadedModule] = field(default_factory=dict)
    react_plugin: Optional[ReactPlugin] = None
    render_options: Optional[RenderOptions] = None

    def __repr__(self) -> str:
        return (
            f"InstalledModule(name={self.name}, description={self.description}, "
            f"entry_points={self.entry_points.keys()}, react_plugin={self.react_plugin is not None}, "
            f"render_options={self.render_options is not None})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def get_installed_modules() -> Dict[str, InstalledModule]:
    named_objects: Dict[str, InstalledModule] = {}

    for ep in pkg_resources.iter_entry_points(group="funcnodes.module"):
        try:
            loaded = ep.load()  # should fail first

            if ep.module_name not in named_objects:
                named_objects[ep.module_name] = InstalledModule(
                    name=ep.module_name,
                    entry_points={},
                    module=None,
                )

            named_objects[ep.module_name].entry_points[ep.name] = {
                "name": ep.name,
                "object": loaded,
            }
            if ep.name == "module":
                named_objects[ep.module_name].module = loaded

            if not named_objects[ep.module_name].description:
                try:
                    package_metadata = metadata(ep.dist.project_name)
                    description = package_metadata.get(
                        "Summary", "No description available"
                    )
                except Exception as e:
                    description = f"Could not retrieve description: {str(e)}"
                named_objects[ep.module_name].description = description

        except Exception:
            continue

    return named_objects
