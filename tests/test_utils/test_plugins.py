import builtins
import types

import pytest

from funcnodes_core.utils.plugins import assert_module_metadata, InstalledModule
from funcnodes_core.utils import plugins as plugins_module
from importlib.metadata import PackageNotFoundError


class DummyDistribution:
    def __init__(self, summary: str, version: str):
        self.metadata = {"Summary": summary}
        self.version = version


def test_assert_module_metadata_populates_from_distribution(monkeypatch):
    """When the distribution can be resolved directly it should populate metadata."""

    dist = DummyDistribution(summary="Direct summary", version="1.0.1")
    modulde_data = InstalledModule(name="demo", module=None)

    def fake_from_name(cls, name):
        assert name == "demo"
        return dist

    monkeypatch.setattr(
        plugins_module.Distribution, "from_name", classmethod(fake_from_name)
    )
    monkeypatch.setattr(plugins_module, "entry_points", lambda **kwargs: [])

    result = assert_module_metadata(modulde_data)

    assert result.description == "Direct summary"
    assert result.version == "1.0.1"


def test_assert_module_metadata_falls_back_to_entry_point_dist(monkeypatch):
    """When Distribution.from_name fails the entry point dist should be used."""

    fallback_dist = DummyDistribution(summary="Fallback summary", version="9.9.9")
    modulde_data = InstalledModule(name="demo_ep", module=None)

    def fake_from_name(cls, name):
        raise PackageNotFoundError(name)

    class DummyEntryPoint:
        def __init__(self, module, dist):
            self.module = module
            self.dist = dist

    def fake_entry_points(**kwargs):
        if kwargs.get("module") == "demo_ep":
            return [DummyEntryPoint("demo_ep", fallback_dist)]
        return []

    monkeypatch.setattr(
        plugins_module.Distribution, "from_name", classmethod(fake_from_name)
    )
    monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)

    result = assert_module_metadata(modulde_data)

    assert result.description == "Fallback summary"
    assert result.version == "9.9.9"


def test_assert_module_metadata_handles_missing_distribution(monkeypatch):
    """If no distribution can be resolved description falls back to an error message."""

    module_name = "ghost_pkg"
    modulde_data = InstalledModule(name=module_name, module=None)

    def fake_from_name(cls, name):
        assert name == module_name
        raise PackageNotFoundError(name)

    class DummyEntryPoint:
        def __init__(self):
            self.module = module_name

        @property
        def dist(self):
            raise PackageNotFoundError("dist missing")

    monkeypatch.setattr(
        plugins_module.Distribution, "from_name", classmethod(fake_from_name)
    )
    monkeypatch.setattr(
        plugins_module, "entry_points", lambda **kwargs: [DummyEntryPoint()]
    )

    result = assert_module_metadata(modulde_data)

    assert result.description.startswith("Could not retrieve description")
    assert result.version is None


def test_assert_entry_points_loaded_handles_success_and_failure(monkeypatch):
    """Entry points should populate module data and log load errors."""

    loaded_values = {"module": object(), "other": object()}

    class DummyEntryPoint:
        def __init__(self, name, *, raises=False):
            self.name = name
            self.module = "demo"
            self.dist = None
            self.raises = raises

        def load(self):
            if self.raises:
                raise RuntimeError(f"boom-{self.name}")
            return loaded_values[self.name]

    entry_point_calls = []

    def fake_entry_points(**kwargs):
        entry_point_calls.append(kwargs)
        assert kwargs == {"group": "funcnodes.module", "module": "demo"}
        return [
            DummyEntryPoint("module"),
            DummyEntryPoint("other"),
            DummyEntryPoint("broken", raises=True),
        ]

    captured_logs = []

    monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)
    monkeypatch.setattr(
        plugins_module.FUNCNODES_LOGGER,
        "exception",
        lambda message: captured_logs.append(message),
    )

    module = InstalledModule(name="demo", module=None)
    result = plugins_module.assert_entry_points_loaded(module)

    assert entry_point_calls, "entry_points should be queried"
    assert result.entry_points["other"] is loaded_values["other"]
    assert result.module is loaded_values["module"]
    assert captured_logs and "broken" in captured_logs[0]


def test_assert_entry_points_loaded_skips_existing_entries(monkeypatch):
    """Existing entry names should not be reloaded or replaced."""

    load_calls = []

    class DummyEntryPoint:
        def __init__(self, name):
            self.name = name
            self.module = "demo"
            self.dist = None

        def load(self):
            load_calls.append(self.name)
            raise AssertionError("load should not be called for existing entries")

    def fake_entry_points(**kwargs):
        assert kwargs == {"group": "funcnodes.module", "module": "demo"}
        return [DummyEntryPoint("preloaded")]

    monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)

    already_loaded = object()
    module = InstalledModule(
        name="demo", module=None, entry_points={"preloaded": already_loaded}
    )

    result = plugins_module.assert_entry_points_loaded(module)

    assert load_calls == []
    assert result.entry_points["preloaded"] is already_loaded


def test_reload_plugin_module_reloads_existing_module(monkeypatch):
    """Reload path should refresh existing modules and keep metadata pipeline."""

    fake_module = types.ModuleType("demo_pkg")

    reloaded = []

    def fake_reload(module):
        reloaded.append(module)
        return module

    monkeypatch.setitem(plugins_module.sys.modules, "demo_pkg", fake_module)
    monkeypatch.setattr(plugins_module, "reload", fake_reload)
    monkeypatch.setattr(plugins_module, "entry_points", lambda **kwargs: [])

    def fake_assert_entry_points_loaded(data):
        data.entry_points["sentinel"] = True
        return data

    def fake_assert_module_metadata(data):
        data.description = "loaded"
        data.version = "0.1"
        return data

    monkeypatch.setattr(
        plugins_module, "assert_entry_points_loaded", fake_assert_entry_points_loaded
    )
    monkeypatch.setattr(
        plugins_module, "assert_module_metadata", fake_assert_module_metadata
    )

    result = plugins_module.reload_plugin_module("demo_pkg")

    assert reloaded == [fake_module]
    assert result.entry_points["sentinel"] is True
    assert result.description == "loaded"
    assert result.version == "0.1"


def test_reload_plugin_module_import_error_propagates(monkeypatch):
    """Missing modules should log and re-raise ImportError."""

    captured_logs = []

    monkeypatch.setattr(
        plugins_module.FUNCNODES_LOGGER,
        "exception",
        lambda message: captured_logs.append(message),
    )

    real_import = builtins.__import__

    def raising_import(name, *args, **kwargs):
        if name == "missing.pkg":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", raising_import)
    monkeypatch.setattr(plugins_module, "entry_points", lambda **kwargs: [])

    with pytest.raises(ImportError):
        plugins_module.reload_plugin_module("missing.pkg")

    assert captured_logs
    assert "missing.pkg" in captured_logs[0]


def test_get_installed_modules_deduplicates_and_updates(monkeypatch):
    """get_installed_modules should reload missing entries once and enrich data."""

    class GroupEntryPoint:
        def __init__(self, module):
            self.module = module

    group_eps = [
        GroupEntryPoint("alpha"),
        GroupEntryPoint("beta"),
        GroupEntryPoint("alpha"),  # duplicate to ensure deduplication
    ]

    def fake_entry_points(**kwargs):
        assert kwargs == {"group": "funcnodes.module"}
        return group_eps

    reloaded = []

    def fake_reload(name):
        reloaded.append(name)
        return InstalledModule(name=name, module=None)

    def fake_assert_entry_points_loaded(data):
        data.entry_points["loaded"] = True
        return data

    def fake_assert_module_metadata(data):
        data.description = f"desc:{data.name}"
        return data

    existing = InstalledModule(name="beta", module=object())

    monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)
    monkeypatch.setattr(plugins_module, "reload_plugin_module", fake_reload)
    monkeypatch.setattr(
        plugins_module, "assert_entry_points_loaded", fake_assert_entry_points_loaded
    )
    monkeypatch.setattr(
        plugins_module, "assert_module_metadata", fake_assert_module_metadata
    )

    result = plugins_module.get_installed_modules(named_objects={"beta": existing})

    assert reloaded == ["alpha"]
    assert set(result.keys()) == {"alpha", "beta"}
    assert result["alpha"].entry_points["loaded"] is True
    assert result["beta"].entry_points["loaded"] is True
    assert result["beta"].description == "desc:beta"


def test_get_installed_modules_initializes_when_named_objects_missing(monkeypatch):
    """Calling get_installed_modules without a cache should create and populate one."""

    class GroupEntryPoint:
        def __init__(self, module):
            self.module = module

    class ModuleEntryPoint:
        def __init__(self, name, value, dist):
            self.name = name
            self.module = dist.name
            self.dist = dist
            self._value = value

        def load(self):
            return self._value

    class DummyDistribution:
        def __init__(self, name):
            self.name = name
            self.metadata = {"Summary": f"Summary for {name}"}
            self.version = "2.0"

    module_name = "solo_pkg"
    module_obj = types.ModuleType(module_name)
    monkeypatch.setitem(plugins_module.sys.modules, module_name, module_obj)

    reload_calls = []
    monkeypatch.setattr(
        plugins_module,
        "reload",
        lambda module: reload_calls.append(module.__name__) or module,
    )

    def fake_entry_points(**kwargs):
        assert kwargs.get("group") == "funcnodes.module"
        if "module" in kwargs:
            dist = DummyDistribution(kwargs["module"])
            return [
                ModuleEntryPoint("module", module_obj, dist),
                ModuleEntryPoint("other", object(), dist),
            ]
        return [GroupEntryPoint(module_name)]

    def fake_from_name(cls, name):
        return DummyDistribution(name)

    monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)
    monkeypatch.setattr(
        plugins_module.Distribution, "from_name", classmethod(fake_from_name)
    )

    result = plugins_module.get_installed_modules()

    assert module_name in result
    assert reload_calls == [module_name]
    installed = result[module_name]
    assert installed.module is module_obj
    assert installed.entry_points["other"] is not None
    assert installed.description == f"Summary for {module_name}"
    assert installed.version == "2.0"


def test_register_setup_plugin_records_callable(monkeypatch):
    """register_setup_plugin should map callables by their module name."""

    monkeypatch.setattr(plugins_module, "PLUGIN_FUNCTIONS", {})

    def sample(installed):
        return installed

    plugins_module.register_setup_plugin(sample)

    assert sample.__module__ in plugins_module.PLUGIN_FUNCTIONS
    assert plugins_module.PLUGIN_FUNCTIONS[sample.__module__] is sample
