"""Tests for the lib module."""

import types

from funcnodes_core.lib import (
    Library,
    Shelf,
    check_shelf,
    flatten_shelf,
    module_to_shelf,
    serialize_shelf,
)
from funcnodes_core.nodemaker import NodeDecorator
from pytest_funcnodes import funcnodes_test

import pytest


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
