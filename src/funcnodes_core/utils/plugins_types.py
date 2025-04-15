from typing import Dict, Any, Optional, TypedDict, List
from dataclasses import dataclass, field


class RenderOptions(TypedDict, total=False):
    """
    A typed dictionary for render options.

    Attributes:
      typemap (dict[str, str]): A dictionary mapping types to strings.
      inputconverter (dict[str, str]): A dictionary mapping input types to strings.
    """

    typemap: dict[str, str]
    inputconverter: dict[str, str]


class BasePlugin(TypedDict):
    """
    A typed dictionary for a base plugin.

    Attributes:
      description (str): The description of the plugin.
      entry_points (Dict[str, Any]): Dictionary of entry points for the plugin.
    """

    module: str


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
    entry_points: Dict[str, Any] = field(default_factory=dict)
    plugins: List[BasePlugin] = field(default_factory=list)
    render_options: Optional[RenderOptions] = None
    version: Optional[str] = None
    _is_setup = False

    @property
    def rep_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "entry_points": list(self.entry_points.keys()),
            "version": self.version,
            "plugins": [p["module"] for p in self.plugins],
            "render_options": self.render_options is not None,
        }

    def __repr__(self) -> str:
        return f"InstalledModule({', '.join(f'{k}={v}' for k, v in self.rep_dict.items())})"

    def __str__(self) -> str:
        return self.__repr__()
