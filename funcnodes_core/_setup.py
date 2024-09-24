from typing import Optional
from .config import RenderOptions, update_render_options
from .lib import check_shelf
from dataclasses import dataclass
from ._logging import FUNCNODES_LOGGER
from .utils.plugins import get_installed_modules, InstalledModule

try:
    from funcnodes_react_flow import add_react_plugin, ReactPlugin
except (ModuleNotFoundError, ImportError):

    def add_react_plugin(*args, **kwargs):
        pass

    ReactPlugin = dict


@dataclass
class ModuleData:
    module: object
    react_plugin: Optional[ReactPlugin] = None
    render_options: Optional[RenderOptions] = None


def setup_module(mod_data: InstalledModule):
    entry_points = mod_data.setdefault("entry_points", {})
    mod = mod_data["module"]
    if not mod:
        return None
    if "react_plugin" in entry_points:
        add_react_plugin(mod, entry_points["react_plugin"])
    elif hasattr(mod, "REACT_PLUGIN"):
        add_react_plugin(mod, mod.REACT_PLUGIN)
        entry_points["react_plugin"] = mod.REACT_PLUGIN

    if "render_options" in entry_points:
        update_render_options(entry_points["render_options"])
    elif hasattr(mod, "FUNCNODES_RENDER_OPTIONS"):
        update_render_options(mod.FUNCNODES_RENDER_OPTIONS)
        entry_points["render_options"] = mod.FUNCNODES_RENDER_OPTIONS

    if "shelf" not in entry_points:
        for sn in ["NODE_SHELF", "NODE_SHELFE"]:
            if hasattr(mod, sn):
                entry_points["shelf"] = getattr(mod, sn)
                break
    if "shelf" in entry_points:
        try:
            check_shelf(entry_points["shelf"])
        except ValueError as e:
            FUNCNODES_LOGGER.error("Error in module %s: %s" % (mod.__name__, e))
            del entry_points["shelf"]
    return mod_data


AVAILABLE_MODULES = {}


def setup():
    for name, mod in get_installed_modules().items():
        mod = setup_module(mod)
        if mod:
            AVAILABLE_MODULES[name] = mod
