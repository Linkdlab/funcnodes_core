from typing import Dict

from importlib.metadata import entry_points
from .._logging import FUNCNODES_LOGGER
from .plugins_types import InstalledModule


def get_installed_modules() -> Dict[str, InstalledModule]:
    named_objects: Dict[str, InstalledModule] = {}

    for ep in entry_points(group="funcnodes.module"):
        try:
            loaded = ep.load()  # should fail first
            module_name = ep.value

            if module_name not in named_objects:
                named_objects[module_name] = InstalledModule(
                    name=module_name,
                    entry_points={},
                    module=None,
                )

            named_objects[module_name].entry_points[ep.name] = loaded
            if ep.name == "module":
                named_objects[module_name].module = loaded

            if not named_objects[module_name].description:
                try:
                    package_metadata = ep.dist.metadata
                    description = package_metadata.get(
                        "Summary", "No description available"
                    )
                except Exception as e:
                    description = f"Could not retrieve description: {str(e)}"
                named_objects[module_name].description = description

        except Exception as exc:
            FUNCNODES_LOGGER.exception(exc)

    return named_objects
