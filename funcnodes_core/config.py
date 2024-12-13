import os
import json
from .utils.data import deep_fill_dict
from .utils.plugins_types import RenderOptions
from dotenv import load_dotenv
from exposedfunctionality.function_parser.types import type_to_string
import tempfile
import shutil
import sys

load_dotenv(override=True)


BASE_CONFIG_DIR = os.environ.get(
    "FUNCNODES_CONFIG_DIR", os.path.join(os.path.expanduser("~"), ".funcnodes")
)

DEFAULT_CONFIG = {
    "env_dir": os.path.join(BASE_CONFIG_DIR, "env"),
    "worker_manager": {
        "host": "127.0.0.1",
        "port": 9380,
    },
    "frontend": {
        "port": 8000,
    },
}


CONFIG = DEFAULT_CONFIG
CONFIG_DIR = BASE_CONFIG_DIR


def write_config(path, config):
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
    with open(path, "w+") as f:
        json.dump(config, f, indent=2)

    with open(path + ".bu", "w+") as f:
        json.dump(config, f, indent=2)


def load_config(path):
    """
    Loads the configuration file.

    Args:
      path (str): The path to the configuration file.

    Returns:
      None

    Examples:
      >>> load_config("config.json")
    """
    global CONFIG
    config = None
    try:
        with open(path, "r") as f:
            config = json.load(f)
    except Exception:
        pass

    if config is None:
        try:
            with open(path + ".bu", "r") as f:
                config = json.load(f)
        except Exception:
            pass

    if config is None:
        config = DEFAULT_CONFIG

    deep_fill_dict(config, DEFAULT_CONFIG)
    write_config(path, config)
    CONFIG = config


def check_config_dir():
    """
    Checks the configuration directory.

    Returns:
      None

    Examples:
      >>> check_config_dir()
    """
    global CONFIG_DIR
    if not os.path.exists(BASE_CONFIG_DIR):
        os.makedirs(BASE_CONFIG_DIR)
    load_config(os.path.join(BASE_CONFIG_DIR, "config.json"))
    if "custom_config_dir" in CONFIG:
        load_config(os.path.join(CONFIG["custom_config_dir"], "config.json"))
        CONFIG_DIR = CONFIG["custom_config_dir"]
    else:
        CONFIG_DIR = BASE_CONFIG_DIR


check_config_dir()


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
            del options["typemap"][k]
            k = type_to_string(k)
            options["inputconverter"][k] = v
        if not isinstance(v, str):
            v = type_to_string(v)
            options["inputconverter"][k] = v
        FUNCNODES_RENDER_OPTIONS["inputconverter"][k] = v

    # make sure its json serializable
    try:
        json.dumps(options)
    except json.JSONDecodeError:
        return
    deep_fill_dict(
        FUNCNODES_RENDER_OPTIONS, options, merge_lists=True, unfify_lists=True
    )


IN_NODE_TEST = False


class This(sys.__class__):  # sys.__class__ is <class 'module'>
    _IN_NODE_TEST = IN_NODE_TEST

    @property
    def IN_NODE_TEST(self):  # do the property things in this class
        return self._IN_NODE_TEST

    @IN_NODE_TEST.setter
    def IN_NODE_TEST(self, value):  # setter is also OK
        value = bool(value)
        # if value is the same as the current value, do nothing
        if value == self._IN_NODE_TEST:
            return
        if value:
            set_in_test()
        self._IN_NODE_TEST = value


del IN_NODE_TEST

sys.modules[__name__].__class__ = This  # set the __class__ of the module to This


def set_in_test(clear=True):
    """
    Sets the configuration to be in test mode.

    Returns:
      None

    Examples:
      >>> set_in_test()
    """
    global BASE_CONFIG_DIR
    sys.modules[__name__]._IN_NODE_TEST = True
    BASE_CONFIG_DIR = os.path.join(tempfile.gettempdir(), "funcnodes_test")
    if clear:
        if os.path.exists(BASE_CONFIG_DIR):
            try:
                shutil.rmtree(BASE_CONFIG_DIR)
            except Exception:
                pass
    check_config_dir()

    # import here to avoid circular import

    from ._logging import set_logging_dir  # noqa C0415 # pylint: disable=import-outside-toplevel

    set_logging_dir(os.path.join(BASE_CONFIG_DIR, "logs"))


sys.modules[__name__].IN_NODE_TEST = bool(os.environ.get("IN_NODE_TEST", False))
