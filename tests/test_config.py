import importlib
import json
import os
import warnings

import pytest
import pytest_funcnodes

import funcnodes_core as fn
from funcnodes_core.config import FuncNodesDeprecationWarning
from pytest_funcnodes import teardown


def test_in_node_test_varaset():
    try:
        # assert a warning is issued when accessing the deprecated attribute
        with pytest.warns(FuncNodesDeprecationWarning):
            fn.config.set_in_test()

        assert pytest_funcnodes.get_in_test()
        pid = os.getpid()
        assert os.path.basename(fn.config._BASE_CONFIG_DIR) == f"funcnodes_test_{pid}"
    finally:
        teardown()


def test_config_access_deprecation():
    # make sure a deprecation warning is issued when accessing the deprecated attributes
    with pytest.warns(DeprecationWarning):
        fn.config.CONFIG
    with pytest.warns(DeprecationWarning):
        fn.config.CONFIG_DIR
    with pytest.warns(DeprecationWarning):
        fn.config.BASE_CONFIG_DIR


def test_no_deprecation_warning():
    # make sure no deprecation warning is issued when accessing the new attribute
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)


def test_config_not_laoded():
    try:
        assert not fn.config._CONFIG_CHANGED, "Expected _CONFIG_CHANGED to be False"

        pytest_funcnodes.set_in_test()
        assert fn.config._CONFIG_CHANGED, "Expected _CONFIG_CHANGED to be True"
    finally:
        teardown()


def test_load_config_prefers_backup_when_primary_missing(tmp_path):
    config_module = importlib.reload(fn.config)
    config_path = tmp_path / "config.json"
    backup_path = config_path.with_suffix(".json.bu")
    backup_payload = {"frontend": {"port": 4242}}
    backup_path.write_text(json.dumps(backup_payload))

    try:
        config_module.load_config(config_path)
        assert config_module._CONFIG["frontend"]["port"] == 4242
        assert config_path.exists()
        assert backup_path.exists()
    finally:
        importlib.reload(fn.config)


def test_check_config_dir_uses_custom_config_directory(monkeypatch, tmp_path):
    base_dir = tmp_path / "base"
    custom_dir = tmp_path / "custom"
    base_dir.mkdir()
    custom_dir.mkdir()

    base_config = {"custom_config_dir": str(custom_dir)}
    (base_dir / "config.json").write_text(json.dumps(base_config))
    custom_payload = {"frontend": {"host": "custom-host"}}
    (custom_dir / "config.json").write_text(json.dumps(custom_payload))

    monkeypatch.setenv("FUNCNODES_CONFIG_DIR", str(base_dir))
    config_module = importlib.reload(fn.config)

    try:
        config_module.check_config_dir()
        assert config_module.get_config_dir() == custom_dir.resolve()
        assert config_module.get_config()["frontend"]["host"] == "custom-host"
    finally:
        importlib.reload(fn.config)


def test_update_render_options_handles_non_string_inputconverter(monkeypatch):
    monkeypatch.setattr(
        fn.config,
        "FUNCNODES_RENDER_OPTIONS",
        {"typemap": {}, "inputconverter": {}},
    )

    fn.config.update_render_options(
        {
            "inputconverter": {int: bool},
            "typemap": {int: bool},
        }
    )

    from exposedfunctionality.function_parser.types import type_to_string

    expected_key = type_to_string(int)
    expected_value = type_to_string(bool)

    assert (
        fn.config.FUNCNODES_RENDER_OPTIONS["inputconverter"][expected_key]
        == expected_value
    )
    assert fn.config.FUNCNODES_RENDER_OPTIONS["typemap"][expected_key] == expected_value


def test_update_render_options_ignores_non_dict_input(monkeypatch):
    monkeypatch.setattr(
        fn.config,
        "FUNCNODES_RENDER_OPTIONS",
        {"typemap": {}, "inputconverter": {}},
    )

    fn.config.update_render_options(None)

    assert fn.config.FUNCNODES_RENDER_OPTIONS == {"typemap": {}, "inputconverter": {}}


def test_update_render_options_initializes_missing_sections(monkeypatch):
    monkeypatch.setattr(
        fn.config,
        "FUNCNODES_RENDER_OPTIONS",
        {"typemap": {}, "inputconverter": {}},
    )

    options = {}
    fn.config.update_render_options(options)

    assert options["typemap"] == {}
    assert options["inputconverter"] == {}


def test_update_render_options_returns_on_json_serialization_failure(monkeypatch):
    monkeypatch.setattr(
        fn.config,
        "FUNCNODES_RENDER_OPTIONS",
        {"typemap": {}, "inputconverter": {}},
    )

    options = {
        "typemap": {},
        "inputconverter": {},
        "extra": {"unsupported": {1, 2, 3}},
    }

    fn.config.update_render_options(options)

    assert fn.config.FUNCNODES_RENDER_OPTIONS == {"typemap": {}, "inputconverter": {}}
