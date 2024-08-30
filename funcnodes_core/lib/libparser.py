from typing import Optional
from .lib import Shelf, Node
import inspect
from warnings import warn
from .._logging import FUNCNODES_LOGGER
from .._setup import setup_module


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

    mod_data = setup_module({"module": mod})

    if "shelf" in mod_data:
        shelf = mod_data["shelf"]
        if (
            isinstance(shelf, dict)
            and "nodes" in shelf
            and "subshelves" in shelf
            and "name" in shelf
        ):
            return shelf

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

            shelf["nodes"].append(obj)
    #            if obj.__name__ != name:
    #                shelf["nodes"][name] = obj
    #                if obj.__name__ not in mod_dict:
    #                    mod_dict[obj.__name__] = obj
    return shelf
