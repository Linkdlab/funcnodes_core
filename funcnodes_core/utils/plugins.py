from typing import Dict, Any, TypedDict


import pkg_resources

from importlib.metadata import metadata


class LoadedModule(TypedDict):
    """
    TypedDict for an individual loaded module.

    Attributes:
        name (str): The name of the entry point.
        object (Any): The actual object loaded from the entry point.
    """

    name: str
    object: Any


class InstalledModule(TypedDict):
    """
    TypedDict for an installed module.

    Attributes:
        description (str): The description of the module.
        entry_points (Dict[str, LoadedModule]): Dictionary of entry points for the module.
    """

    description: str
    entry_points: Dict[str, LoadedModule]
    module: Any


def get_installed_modules() -> Dict[str, InstalledModule]:
    named_objects: Dict[str, InstalledModule] = {}

    for ep in pkg_resources.iter_entry_points(group="funcnodes.module"):
        try:
            loaded = ep.load()  # should fail first

            if ep.module_name not in named_objects:
                named_objects[ep.module_name] = {
                    "description": None,
                    "entry_points": {},
                    "module": None,
                }

            named_objects[ep.module_name]["entry_points"][ep.name] = {
                "name": ep.name,
                "object": loaded,
            }
            if ep.name == "module":
                named_objects[ep.module_name]["module"] = loaded

            if not named_objects[ep.module_name]["description"]:
                try:
                    package_metadata = metadata(ep.dist.project_name)
                    description = package_metadata.get(
                        "Summary", "No description available"
                    )
                except Exception as e:
                    description = f"Could not retrieve description: {str(e)}"
                named_objects[ep.module_name]["description"] = description

        except Exception:
            continue

    return named_objects
