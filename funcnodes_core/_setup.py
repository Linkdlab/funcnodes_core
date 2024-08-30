from typing import Optional
from .config import RenderOptions, update_render_options
from . import utils
from .lib import check_shelf
from dataclasses import dataclass
from ._logging import FUNCNODES_LOGGER

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


def setup_module(mod_data):
    mod = mod_data["module"]
    if "react_plugin" in mod_data:
        add_react_plugin(mod, mod_data["react_plugin"])
    elif hasattr(mod, "REACT_PLUGIN"):
        add_react_plugin(mod, mod.REACT_PLUGIN)
        mod_data["react_plugin"] = mod.REACT_PLUGIN

    if "render_options" in mod_data:
        update_render_options(mod_data["render_options"])
    elif hasattr(mod, "FUNCNODES_RENDER_OPTIONS"):
        update_render_options(mod.FUNCNODES_RENDER_OPTIONS)
        mod_data["render_options"] = mod.FUNCNODES_RENDER_OPTIONS

    if "shelf" not in mod_data:
        for sn in ["NODE_SHELF", "NODE_SHELFE"]:
            if hasattr(mod, sn):
                mod_data["shelf"] = getattr(mod, sn)
                break
    if "shelf" in mod_data:
        try:
            check_shelf(mod_data["shelf"])
        except ValueError as e:
            FUNCNODES_LOGGER.error("Error in module %s: %s" % (mod.__name__, e))
            del mod_data["shelf"]
    return mod_data


def setup():
    for mod in utils.plugins.get_installed_modules().values():
        setup_module(mod)
