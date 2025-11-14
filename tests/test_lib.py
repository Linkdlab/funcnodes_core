"""Tests for the lib module."""

import itertools
import types
import weakref

from funcnodes_core.lib import (
    Library,
    Shelf,
    NodeClassNotFoundError,
    ShelfExistsError,
    ShelfNotFoundError,
    ShelfPathError,
    ShelfTypeError,
    check_shelf,
    flatten_shelf,
    module_to_shelf,
    serialize_shelf,
)
from funcnodes_core.node import Node, REGISTERED_NODES
from funcnodes_core.nodemaker import NodeDecorator
from pytest_funcnodes import funcnodes_test

import pytest


_NODE_COUNTER = itertools.count()


@pytest.fixture
def make_node():
    def _factory(prefix: str = "lib_node"):
        idx = next(_NODE_COUNTER)
        node_id = f"{prefix}_{idx}"

        @NodeDecorator(node_id=node_id, name=f"{prefix}_{idx}")
        def generated_node(payload: str = "payload") -> str:
            """Simple node used for Library tests."""
            return payload

        return generated_node

    return _factory


def _make_node_class(module_name: str, class_name: str, node_id: str):
    async def _func(self, *args, **kwargs):
        return None

    return type(
        class_name,
        (Node,),
        {
            "__module__": module_name,
            "node_id": node_id,
            "node_name": class_name,
            "func": _func,
        },
    )


@pytest.fixture
def testfunc():
    @NodeDecorator("test_lib_testfunc", name="testfunc")
    def testfunc_def(int: int, str: str) -> str:
        """Test function for testing the lib module.
        Args:
            int (int): An integer.
            str (str): A string.

        Returns:
            str: A string.
        """
        return str * int

    return testfunc_def


@pytest.fixture
def node_shelf(testfunc):
    return {
        "description": "Tests for the lib module.",
        "name": "test_lib",
        "nodes": [testfunc],
        "subshelves": [],
    }


def test_module_to_shelf(node_shelf):
    # dynamically create an module with a NODE_SHELF variable
    module = types.ModuleType("test_lib")
    module.NODE_SHELF = node_shelf

    expected = {
        "description": "Tests for the lib module.",
        "name": "test_lib",
        "nodes": [
            {
                "node_id": "test_lib_testfunc",
                "description": "Test function for testing the lib module.",
                "node_name": "testfunc",
                "inputs": [
                    {
                        "description": "An integer.",
                        "type": "int",
                        "uuid": "int",
                    },
                    {
                        "description": "A string.",
                        "type": "str",
                        "uuid": "str",
                    },
                ],
                "outputs": [
                    {
                        "description": "A string.",
                        "type": "str",
                        "uuid": "out",
                    }
                ],
            }
        ],
        "subshelves": [],
    }

    assert expected == serialize_shelf(
        module_to_shelf(
            module,
            # name has to be set since the module name changes for different test settings
            name="test_lib",
        )
    )


def test_module_to_shelf_collects_nodes_without_entry_point():
    module = types.ModuleType("libparser_fallback")
    module.__doc__ = "Auto-collected nodes"
    node_cls = _make_node_class(module.__name__, "FallbackNode", "lib_fallback_node")
    module.FallbackNode = node_cls

    shelf = module_to_shelf(module, name="custom-shelf-name")

    assert shelf.name == "custom-shelf-name"
    assert shelf.description == "Auto-collected nodes"
    assert shelf.nodes == [node_cls]
    assert shelf.subshelves == []


def test_module_to_shelf_warns_on_interfered_node_name():
    module = types.ModuleType("libparser_warning")
    node_cls = _make_node_class(module.__name__, "ConflictingNode", "lib_conflict_node")
    module.alias = node_cls
    module.__dict__["ConflictingNode"] = object()

    with pytest.warns(
        UserWarning, match="interfered Node name ConflictingNode is defined elsewhere"
    ):
        shelf = module_to_shelf(module, name="libparser_warning")

    assert shelf.nodes == [node_cls]


@funcnodes_test
def test_flatten_shelf(testfunc):
    shelf = Shelf(
        nodes=[testfunc],
        name="0",
        description="level 0",
        subshelves=[
            Shelf(
                nodes=[],
                name="1",
                description="level 1",
                subshelves=[
                    Shelf(
                        nodes=[testfunc],
                        name="2",
                        description="level 2",
                        subshelves=[],
                    )
                ],
            )
        ],
    )
    assert flatten_shelf(shelf)[0] == [testfunc, testfunc]


@funcnodes_test
def test_lib_add_shelf(node_shelf, testfunc):
    lib = Library()
    shelf = lib.add_shelf(check_shelf(node_shelf))

    assert len(lib.shelves) == 1
    assert lib.shelves[0].name == node_shelf["name"]
    assert len(lib.shelves[0].nodes) > 0, (
        f"Expected at least one node but got {len(lib.shelves[0].nodes)}"
    )
    assert lib.shelves[0].nodes[0] == testfunc, (
        f"Expected 'testfunc' but got {lib.shelves[0].nodes}"
    )
    assert lib.shelves[0].subshelves == []
    assert shelf == lib.shelves[0]


@funcnodes_test
def test_lib_add_shelf_twice(node_shelf, testfunc):
    lib = Library()
    shelf = lib.add_shelf(check_shelf(node_shelf))

    assert len(lib.shelves) == 1
    assert lib.shelves[0].name == node_shelf["name"]
    assert lib.shelves[0].nodes[0] == testfunc
    assert lib.shelves[0].subshelves == []
    assert shelf == lib.shelves[0]

    shelf2 = lib.add_shelf(check_shelf(node_shelf))

    assert len(lib.shelves) == 1
    assert lib.shelves[0].name == node_shelf["name"]
    assert lib.shelves[0].nodes[0] == testfunc
    assert len(lib.shelves[0].nodes) == 1
    assert lib.shelves[0].subshelves == []
    assert shelf == lib.shelves[0]
    assert shelf2 == shelf


@funcnodes_test
def test_shelf_unique_nodes(testfunc):
    shelf = Shelf(name="testshelf", nodes=[testfunc, testfunc])
    assert len(shelf.nodes) == 1


@funcnodes_test
def test_shelf_unique_subshelves(testfunc):
    subshelf = Shelf(name="testshelf", nodes=[testfunc, testfunc])
    shelf = Shelf(name="testshelf", subshelves=[subshelf, subshelf])

    assert len(shelf.subshelves) == 1
    assert len(shelf.subshelves[0].nodes) == 1
    assert len(flatten_shelf(shelf)[0]) == 1


def test_library_add_nodes_and_lookup_by_id(make_node):
    lib = Library()
    node_a = make_node("lib_node_a")
    node_b = make_node("lib_node_b")

    lib.add_nodes([node_a], ["Top", "Inner"])
    lib.add_node(node_b, "Top")

    assert lib.find_nodeid(node_a.node_id) == [["Top", "Inner"]]
    assert lib.find_nodeclass(node_b) == [["Top"]]
    assert lib.has_node_id(node_a.node_id) is True
    assert lib.get_node_by_id(node_a.node_id) is node_a

    top_level = lib.shelves
    assert [shelf.name for shelf in top_level] == ["Top"]
    assert [sub.name for sub in top_level[0].subshelves] == ["Inner"]

    # adding the same node again should not duplicate entries
    lib.add_nodes([node_a], ["Top", "Inner"])
    assert lib.find_nodeid(node_a.node_id) == [["Top", "Inner"]]

    lib.remove_nodeclass(node_a)
    assert lib.has_node_id(node_a.node_id) is False

    lib.remove_nodeclasses([node_b])
    assert lib.find_nodeid(node_b.node_id) == []

    with pytest.raises(NodeClassNotFoundError):
        lib.get_node_by_id(node_a.node_id)


def test_library_external_shelf_mount_and_removal(make_node):
    lib = Library()
    root_node = make_node("lib_root")
    root = Shelf(name="Root", nodes=[root_node])
    lib.add_shelf(root)

    with pytest.raises(ShelfExistsError):
        lib.add_external_shelf(Shelf(name="Root"))

    external_top_node = make_node("lib_external_top")
    external_top = Shelf(name="ExternalTop", nodes=[external_top_node])
    lib.add_external_shelf(weakref.ref(external_top))

    child_node = make_node("lib_child")
    external_child = Shelf(name="OriginalChild", nodes=[child_node])
    lib.add_subshelf_weak(
        weakref.ref(external_child),
        parent=["Root"],
        alias="MountedChild",
    )

    assert lib.find_nodeid(child_node.node_id) == [["Root", "MountedChild"]]

    with pytest.raises(ShelfExistsError):
        lib.add_subshelf_weak(external_child, parent=["Root"], alias="MountedChild")

    snapshot = lib.full_serialize()
    assert any(shelf["name"] == "Root" for shelf in snapshot["shelves"])
    assert snapshot == lib._repr_json_()

    lib.remove_shelf_path(["Root", "MountedChild"])
    assert lib.find_nodeid(child_node.node_id) == []

    lib.remove_shelf(weakref.ref(external_top))
    assert lib.find_nodeid(external_top_node.node_id) == []

    lib.remove_shelf_path(["Root"])
    assert lib.shelves == []


@funcnodes_test
def test_add_external_shelf_registers_nodes():
    lib = Library()
    node_cls = _make_node_class(
        "test_lib_external_register", "ExternalNode", "external_register_node"
    )
    external_top = Shelf(name="ExternalTop", nodes=[node_cls])

    REGISTERED_NODES.pop(node_cls.node_id, None)
    assert node_cls.node_id not in REGISTERED_NODES

    try:
        lib.add_external_shelf(external_top)
        assert REGISTERED_NODES[node_cls.node_id] is node_cls
    finally:
        REGISTERED_NODES.pop(node_cls.node_id, None)


@funcnodes_test
def test_add_subshelf_weak_registers_nodes():
    lib = Library()
    parent = Shelf(name="Root")
    lib.add_shelf(parent)

    node_cls = _make_node_class(
        "test_lib_subshelf_register", "ChildNode", "subshelf_register_node"
    )
    external_child = Shelf(name="ExternalChild", nodes=[node_cls])

    REGISTERED_NODES.pop(node_cls.node_id, None)
    assert node_cls.node_id not in REGISTERED_NODES

    try:
        lib.add_subshelf_weak(external_child, parent=["Root"], alias="Mounted")
        assert REGISTERED_NODES[node_cls.node_id] is node_cls
    finally:
        REGISTERED_NODES.pop(node_cls.node_id, None)


def test_add_external_shelf_rejects_list_mount():
    lib = Library()
    external_top = Shelf(name="ExternalTop")

    with pytest.raises(ShelfPathError, match="single shelf name string"):
        lib.add_external_shelf(external_top, mount=["ExternalTop"])


def test_add_subshelf_weak_requires_existing_parent():
    lib = Library()
    external_child = Shelf(name="ExternalChild")

    with pytest.raises(ShelfNotFoundError, match="parent path"):
        lib.add_subshelf_weak(external_child, parent="Missing")


def test_add_shelf_requires_shelf_instances():
    lib = Library()

    with pytest.raises(ShelfTypeError, match="Shelf"):
        lib.add_shelf("not-a-shelf")  # type: ignore[arg-type]


def test_remove_shelf_path_rejects_empty_path():
    lib = Library()

    with pytest.raises(ShelfPathError, match="must not be empty"):
        lib.remove_shelf_path([])
