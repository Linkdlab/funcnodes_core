from typing import Dict, Optional
import gc
from .config import update_render_options
from .lib import check_shelf
from ._logging import FUNCNODES_LOGGER
from .utils.plugins import get_installed_modules, InstalledModule, PLUGIN_FUNCTIONS


def setup_module(mod_data: InstalledModule) -> Optional[InstalledModule]:
    gc.collect()
    entry_points = mod_data.entry_points
    mod = mod_data.module
    if not mod:  # funcnodes modules must have an module entry point
        return None

    # first we try to register the plugin setup function as this might register other functions
    try:
        if "plugin_setup" in entry_points:
            entry_points["plugin_setup"]()
        elif hasattr(mod, "FUNCNODES_PLUGIN_SETUP"):
            mod.FUNCNODES_PLUGIN_SETUP()
            entry_points["render_options"] = mod.FUNCNODES_PLUGIN_SETUP
    except Exception as e:
        FUNCNODES_LOGGER.error("Error in plugin setup %s: %s" % (mod.__name__, e))

    # Then we call the plugin functions
    for pluginf in PLUGIN_FUNCTIONS.values():
        try:
            pluginf(mod_data)
        except Exception as e:
            FUNCNODES_LOGGER.error(
                "Error in setup_module plugin function %s: %s" % (mod.__name__, e)
            )

    if "render_options" in entry_points:
        update_render_options(entry_points["render_options"])
    elif hasattr(mod, "FUNCNODES_RENDER_OPTIONS"):
        update_render_options(mod.FUNCNODES_RENDER_OPTIONS)
        entry_points["render_options"] = mod.FUNCNODES_RENDER_OPTIONS

    if "external_worker" in entry_points:
        pass
    elif hasattr(mod, "FUNCNODES_WORKER_CLASSES"):
        entry_points["external_worker"] = mod.FUNCNODES_WORKER_CLASSES

    if "shelf" not in entry_points:
        for sn in ["NODE_SHELF", "NODE_SHELFE"]:
            if hasattr(mod, sn):
                entry_points["shelf"] = getattr(mod, sn)
                break
    if "shelf" in entry_points:
        try:
            entry_points["shelf"] = check_shelf(
                entry_points["shelf"], parent_id=mod_data.name
            )
        except ValueError as e:
            FUNCNODES_LOGGER.error("Error in module %s: %s" % (mod.__name__, e))
            del entry_points["shelf"]
    mod_data._is_setup = True
    return mod_data


AVAILABLE_MODULES: Dict[str, InstalledModule] = {}


def setup():
    for name, mod in get_installed_modules(AVAILABLE_MODULES).items():
        if not mod._is_setup:
            mod = setup_module(mod)
        if mod:
            AVAILABLE_MODULES[name] = mod
