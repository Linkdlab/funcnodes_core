from typing import Dict, Any, Optional, TypedDict, List
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint


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


class _LazyEntryDict(dict):
    def __getitem__(self, name: str) -> Any:
        value = super().__getitem__(name)
        if isinstance(value, EntryPoint):
            value = value.load()
            self[name] = value
            if hasattr(self, "installed_module"):
                installed_module = getattr(self, "installed_module")
                if installed_module.module is None:
                    if name == "module":
                        installed_module.set_module(value)
                    else:
                        module = self.get("module", None)
                        if module is not None:
                            installed_module.set_module(module)
        return value

    def get(self, name: str, default: Any = None) -> Any:
        if name not in self:
            return default
        return self[name]


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
    entry_points: Dict[str, Any] = field(default_factory=_LazyEntryDict)
    plugins: List[BasePlugin] = field(default_factory=list)
    render_options: Optional[RenderOptions] = None
    version: Optional[str] = None
    _is_setup = False

    # make sure that entrz points is a _LazyEntryDict
    def __post_init__(self):
        if not isinstance(self.entry_points, _LazyEntryDict):
            self.entry_points = _LazyEntryDict(self.entry_points)
        self.entry_points.installed_module = self

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

    def set_module(self, module: Any):
        if self.module is not None:
            if self.module != module:
                raise ValueError(
                    f"Module {self.name} already has a module {self.module} and cannot be set to {module}"
                )
        self.module = module
        if not self._is_setup:
            from .._setup import setup_module

            setup_module(self)

    def _repr_json_(self) -> dict[str, Any]:
        return self.rep_dict
