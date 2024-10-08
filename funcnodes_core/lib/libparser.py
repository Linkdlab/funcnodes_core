from typing import Optional
from .lib import Shelf, Node
import inspect
from warnings import warn
from .._logging import FUNCNODES_LOGGER
from .._setup import setup_module, InstalledModule


def module_to_shelf(mod, name: Optional[str] = None) -> Shelf:
    """
    Parses a single module for Nodes and and returns a filled shelf object.
    """  #

    FUNCNODES_LOGGER.debug(f"parsing module {mod}")
    if not name:
        if hasattr(mod, "__name__"):
            name = str(mod.__name__)

    if not name:
        name = str(mod)

    mod_data = setup_module(InstalledModule(module=mod, name=name, entry_points={}))

    if "shelf" in mod_data.entry_points:
        shelf = mod_data.entry_points["shelf"]
        try:
            shelf = Shelf.from_dict(shelf)
            return shelf
        except Exception as exc:
            FUNCNODES_LOGGER.info(
                f"Error while parsing shelf from entry_points in module {mod}"
            )
            FUNCNODES_LOGGER.exception(exc)

    shelf = Shelf(nodes=[], subshelves=[], name=name, description=mod.__doc__)

    mod_dict = mod.__dict__
    for name, obj in inspect.getmembers(mod):
        # check for not abstract Node
        if (
            inspect.isclass(obj)
            and issubclass(obj, Node)
            and not inspect.isabstract(obj)
        ):
            if name != obj.__name__ and obj.__name__ in mod_dict:
                warn(
                    f"interfered Node name {obj.__name__} is defined elsewhere in module {mod.__name__}"
                )

            shelf.nodes.append(obj)

    return shelf
