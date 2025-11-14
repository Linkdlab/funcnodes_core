from typing import Optional, TypedDict, List, Literal, Dict
from pathlib import Path
import os
import json
from .utils.data import deep_fill_dict, deep_update_dict
from .utils.plugins_types import RenderOptions
from .utils.files import write_json_secure
from dotenv import load_dotenv
from exposedfunctionality.function_parser.types import type_to_string
from .utils.deprecations import (  # noqa: F401
    path_module_attribute_to_getter,
    method_deprecated_decorator,
    FuncNodesDeprecationWarning,  # noqa: F401
)

load_dotenv(override=True)


_BASE_CONFIG_DIR = Path(
    os.environ.get("FUNCNODES_CONFIG_DIR", Path.home() / ".funcnodes")
)


class WorkerManagerConfig(TypedDict, total=False):
    host: str
    port: int


class FrontendConfig(TypedDict, total=False):
    port: int
    host: str


class NodesConfig(TypedDict, total=False):
    default_pretrigger_delay: float


class HandlerConfig(TypedDict, total=False):
    handlerclass: str
    options: dict
    level: str


class LoggingConfig(TypedDict, total=False):
    handler: Dict[str, HandlerConfig]
    level: str


class ConfigType(TypedDict, total=False):
    env_dir: str
    worker_manager: WorkerManagerConfig
    frontend: FrontendConfig
    nodes: NodesConfig
    logging: LoggingConfig


DEFAULT_CONFIG: ConfigType = {
    "env_dir": (_BASE_CONFIG_DIR / "env").as_posix(),
    "worker_manager": {
        "host": "localhost",
        "port": 9380,
    },
    "frontend": {
        "port": 8000,
        "host": "localhost",
    },
    "nodes": {
        "default_pretrigger_delay": float(
            os.environ.get("FUNCNODES_DEFAULT_PRETRIGGER_DELAY", 0.01)
        ),
    },
    "logging": {
        "handler": {
            "console": {
                "handlerclass": "logging.StreamHandler",
                "options": {},
            },
            "file": {
                "handlerclass": "logging.handlers.RotatingFileHandler",
                "options": {
                    "maxBytes": 1024 * 1024 * 5,
                    "backupCount": 5,
                },
            },
        },
    },
}


_CONFIG = DEFAULT_CONFIG
_CONFIG_DIR = _BASE_CONFIG_DIR
_CONFIG_CHANGED = None


def _bupath(path: Path) -> Path:
    """
    Returns the backup path for the configuration file.

    Args:
        path (str): The path to the configuration file.

    Returns:
        str: The backup path.

    Examples:
        >>> _bupath("config.json")
        >>> "config.json.bu"
    """

    return path.with_suffix(path.suffix + ".bu")


def write_config(path: Path, config: ConfigType):
    """
    Writes the configuration file.

    Args:
      path (str): The path to the configuration file.
      config (dict): The configuration to write.

    Returns:
      None

    Examples:
      >>> write_config("config.json", {"env_dir": "env"})
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_secure(config, path, indent=2)
    write_json_secure(config, _bupath(path), indent=2)


def load_config(path: Path):
    """
    Loads the configuration file.

    Args:
      path (str): The path to the configuration file.

    Returns:
      None

    Examples:
      >>> load_config("config.json")
    """
    global _CONFIG
    config: Optional[ConfigType] = None
    path = Path(path)
    try:
        with open(path, "r") as f:
            config = json.load(f)
    except Exception:
        pass

    if config is None:
        try:
            with open(_bupath(path), "r") as f:
                config = json.load(f)
        except Exception:
            pass

    if config is None:
        config = DEFAULT_CONFIG

    deep_fill_dict(config, DEFAULT_CONFIG, inplace=True)
    write_config(path, config)
    _CONFIG = config


def check_config_dir():
    """
    Checks the configuration directory.

    Returns:
      None

    Examples:
      >>> check_config_dir()
    """
    global _CONFIG_DIR, _CONFIG_CHANGED
    _BASE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    load_config(_BASE_CONFIG_DIR / "config.json")
    custom_config_dir = _CONFIG.get("custom_config_dir")
    if custom_config_dir:
        custom_path = Path(custom_config_dir)
        load_config(custom_path / "config.json")
        _CONFIG_DIR = custom_path
    else:
        _CONFIG_DIR = _BASE_CONFIG_DIR

    _CONFIG_CHANGED = False


def get_config_dir() -> Path:
    """
    Returns the configuration directory.

    Returns:
      str: The configuration directory.

    Examples:
      >>> get_config_dir()
    """
    return _CONFIG_DIR.absolute()


def get_config() -> ConfigType:
    """
    Returns the configuration.

    Returns:
      dict: The configuration.

    Examples:
      >>> get_config()
    """
    if _CONFIG_CHANGED:
        reload()
    return _CONFIG


def update_config(config: ConfigType):
    """
    Updates the configuration.

    Args:
      config (dict): The configuration to update.

    Returns:
      None

    Examples:
      >>> update_config({"env_dir": "env"})
    """
    # global _CONFIG
    deep_update_dict(_CONFIG, config, inplace=True)
    write_config(_CONFIG_DIR / "config.json", _CONFIG)
    reload()


FUNCNODES_RENDER_OPTIONS: RenderOptions = {"typemap": {}, "inputconverter": {}}


def update_render_options(options: RenderOptions):
    """
    Updates the render options.

    Args:
      options (RenderOptions): The render options to update.

    Returns:
      None

    Examples:
      >>> update_render_options({"typemap": {"int": "int32"}, "inputconverter": {"str": "string"}})
    """
    if not isinstance(options, dict):
        return
    if "typemap" not in options:
        options["typemap"] = {}
    for k, v in list(options["typemap"].items()):
        if not isinstance(k, str):
            del options["typemap"][k]
            k = type_to_string(k)
            options["typemap"][k] = v

        if not isinstance(v, str):
            v = type_to_string(v)
            options["typemap"][k] = v

    if "inputconverter" not in options:
        options["inputconverter"] = {}
    for k, v in list(options["inputconverter"].items()):
        if not isinstance(k, str):
            del options["inputconverter"][k]
            k = type_to_string(k)
            options["inputconverter"][k] = v
        if not isinstance(v, str):
            v = type_to_string(v)
            options["inputconverter"][k] = v
        FUNCNODES_RENDER_OPTIONS["inputconverter"][k] = v

    # make sure its json serializable
    try:
        json.dumps(options)
    except (json.JSONDecodeError, TypeError):
        return
    deep_fill_dict(
        FUNCNODES_RENDER_OPTIONS, options, merge_lists=True, unify_lists=True
    )


def reload(funcnodes_config_dir: Optional[Path] = None):
    global _CONFIG, _BASE_CONFIG_DIR, _CONFIG_DIR
    load_dotenv(override=True)

    if funcnodes_config_dir is not None:
        os.environ["FUNCNODES_CONFIG_DIR"] = str(Path(funcnodes_config_dir))

    _BASE_CONFIG_DIR = Path(
        os.environ.get("FUNCNODES_CONFIG_DIR", Path.home() / ".funcnodes")
    ).absolute()
    _CONFIG = DEFAULT_CONFIG
    _CONFIG_DIR = _BASE_CONFIG_DIR
    check_config_dir()


def get_in_test() -> bool:
    from pytest_funcnodes import get_in_test as pytest_get_in_test

    return pytest_get_in_test()


get_in_test = method_deprecated_decorator(alternative="pytest_funcnodes.get_in_test")(
    get_in_test
)


def set_in_test(
    in_test: Literal[True] = True,  # noqa: F841  # required for setter
    *,
    clear: bool = True,
    add_pid: bool = True,
    config: Optional[ConfigType] = None,
    fail_on_warnings: Optional[List[Warning]] = None,
):
    from pytest_funcnodes import set_in_test as pytest_set_in_test

    pytest_set_in_test(
        clear=clear, add_pid=add_pid, config=config, fail_on_warnings=fail_on_warnings
    )


set_in_test = method_deprecated_decorator(alternative="pytest_funcnodes.set_in_test")(
    set_in_test
)

CONFIG = path_module_attribute_to_getter(
    __name__,
    "CONFIG",
    get_config,
    None,
)


CONFIG_DIR = path_module_attribute_to_getter(
    __name__,
    "CONFIG_DIR",
    get_config_dir,
    None,
)


def get_base_config_dir() -> Path:
    return _BASE_CONFIG_DIR


BASE_CONFIG_DIR = path_module_attribute_to_getter(
    __name__,
    "BASE_CONFIG_DIR",
    get_base_config_dir,
    None,
)

IN_NODE_TEST = path_module_attribute_to_getter(
    __name__, "IN_NODE_TEST", get_in_test, set_in_test, intital_default=False
)

_CONFIG_CHANGED = True
