from funcnodes_core.utils.plugins_types import InstalledModule


def test_installed_module_rep_dict_reflects_state():
    module = object()
    installed = InstalledModule(
        name="demo",
        module=module,
        description="Demo module",
        entry_points={"alpha": lambda: None, "beta": None},
        plugins=[{"module": "pkg.plugin.Renderer"}],
        render_options={"typemap": {"int": "number"}},
        version="1.2.3",
    )

    rep = installed.rep_dict

    assert rep["name"] == "demo"
    assert rep["description"] == "Demo module"
    assert rep["entry_points"] == ["alpha", "beta"]
    assert rep["version"] == "1.2.3"
    assert rep["plugins"] == ["pkg.plugin.Renderer"]
    assert rep["render_options"] is True


def test_installed_module_str_and_repr_use_rep_dict():
    installed = InstalledModule(
        name="mini",
        module=object(),
    )

    expected = (
        "InstalledModule("
        "name=mini, "
        "description=None, "
        "entry_points=[], "
        "version=None, "
        "plugins=[], "
        "render_options=False)"
    )

    assert repr(installed) == expected
    assert str(installed) == expected
