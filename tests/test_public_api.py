"""Tests for the public package surfaces.

These tests make sure the re-exporting packages stay in sync with the
implementation modules, which also gives coverage to the lightweight
`__init__` modules that would otherwise be missed.
"""

from __future__ import annotations

import importlib

import pytest_funcnodes  # noqa: F401  # ensure plugin import order


def _reload(module_name: str):
    """Import + reload helper so coverage captures module execution."""
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_root_package_reexports_expected_symbols():
    core = _reload("funcnodes_core")

    from funcnodes_core.io import NodeInput as NodeInputImpl
    from funcnodes_core.node import Node as NodeImpl
    from funcnodes_core.lib.lib import Shelf as ShelfImpl, Library as LibraryImpl

    # attribute passthroughs stay in sync with implementation modules
    assert core.NodeInput is NodeInputImpl
    assert core.Node is NodeImpl
    assert core.Shelf is ShelfImpl
    assert core.Library is LibraryImpl

    # module level exports surface documented submodules
    assert core.lib is importlib.import_module("funcnodes_core.lib")
    assert core.nodemaker is importlib.import_module("funcnodes_core.nodemaker")
    assert core.logging is importlib.import_module("funcnodes_core._logging")

    exported = set(core.__all__)
    assert {
        "NodeInput",
        "Node",
        "Shelf",
        "Library",
        "lib",
        "nodemaker",
        "logging",
    }.issubset(exported)


def test_lib_package_reexports_expected_symbols():
    lib_pkg = _reload("funcnodes_core.lib")

    from funcnodes_core.lib.lib import (
        Shelf as ShelfImpl,
        flatten_shelf,
        flatten_shelves,
        check_shelf,
        get_node_in_shelf,
    )
    from funcnodes_core.lib.libparser import module_to_shelf
    from funcnodes_core.lib.libfinder import find_shelf, ShelfDict

    assert lib_pkg.Shelf is ShelfImpl
    assert lib_pkg.flatten_shelf is flatten_shelf
    assert lib_pkg.flatten_shelves is flatten_shelves
    assert lib_pkg.check_shelf is check_shelf
    assert lib_pkg.get_node_in_shelf is get_node_in_shelf
    assert lib_pkg.module_to_shelf is module_to_shelf
    assert lib_pkg.find_shelf is find_shelf
    assert lib_pkg.ShelfDict is ShelfDict

    exported = set(lib_pkg.__all__)
    assert {
        "Shelf",
        "module_to_shelf",
        "serialize_shelf",
        "FullLibJSON",
        "Library",
        "find_shelf",
        "NodeClassNotFoundError",
        "get_node_in_shelf",
        "ShelfDict",
        "flatten_shelf",
        "flatten_shelves",
        "check_shelf",
    }.issubset(exported)
