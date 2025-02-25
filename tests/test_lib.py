"""Tests for the lib module."""

import unittest
import sys
from funcnodes_core.nodemaker import NodeDecorator
from funcnodes_core.lib import (
    module_to_shelf,
    serialize_shelfe,
    flatten_shelf,
    Shelf,
    Library,
    ShelfReferenceLost,
)
import gc

import funcnodes_core as fn

fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])


@NodeDecorator("test_lib_testfunc")
def testfunc(int: int, str: str) -> str:
    """Test function for testing the lib module.
    Args:
        int (int): An integer.
        str (str): A string.

    Returns:
        str: A string.
    """
    return str * int


NODE_SHELF = {
    "description": "Tests for the lib module.",
    "name": "test_lib",
    "nodes": [testfunc],
    "subshelves": [],
}


class TestLib(unittest.TestCase):
    def test_module_to_shelf(self):
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
        self.maxDiff = None

        self.assertEqual(
            expected,
            serialize_shelfe(
                module_to_shelf(
                    sys.modules[self.__module__],
                    # name has to be set since the module name changes for different test settings
                    name="test_lib",
                )
            ),
        )

    def test_flatten_shelf(self):
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
        self.assertEqual([testfunc, testfunc], flatten_shelf(shelf)[0])

    def test_lib_shelf_loseref(self):
        lib = Library()
        lib.add_shelf(NODE_SHELF)
        gc.collect()
        with self.assertRaises(ShelfReferenceLost):
            print(lib.shelves)

    def test_lib_add_shelf(self):
        lib = Library()
        s = lib.add_shelf(NODE_SHELF)  # keep the shelf reference
        self.assertEqual(len(lib.shelves), 1)
        self.assertEqual(lib.shelves[0].name, NODE_SHELF["name"])
        self.assertEqual(lib.shelves[0].nodes[0], testfunc)
        self.assertEqual(lib.shelves[0].subshelves, [])
        self.assertEqual(s, lib.shelves[0])

    def test_lib_add_shelf_twice(self):
        lib = Library()
        s = lib.add_shelf(NODE_SHELF)  # keep the shelf reference
        self.assertEqual(len(lib.shelves), 1)
        self.assertEqual(lib.shelves[0].name, NODE_SHELF["name"])
        self.assertEqual(lib.shelves[0].nodes[0], testfunc)
        self.assertEqual(lib.shelves[0].subshelves, [])
        self.assertEqual(s, lib.shelves[0])

        s2 = lib.add_shelf(NODE_SHELF)  # keep the shelf reference
        self.assertEqual(len(lib.shelves), 1)
        self.assertEqual(lib.shelves[0].name, NODE_SHELF["name"])
        self.assertEqual(lib.shelves[0].nodes[0], testfunc)
        self.assertEqual(len(lib.shelves[0].nodes), 1)
        self.assertEqual(lib.shelves[0].subshelves, [])
        self.assertEqual(s, lib.shelves[0])
        self.assertEqual(s2, s)

    def test_shelf_unique_nodes(self):
        shelf = Shelf(name="testshelf", nodes=[testfunc, testfunc])
        self.assertEqual(len(shelf.nodes), 1)

    def test_shelf_unique_subshelves(self):
        subshelf = Shelf(name="testshelf", nodes=[testfunc, testfunc])
        shelf = Shelf(name="testshelf", subshelves=[subshelf, subshelf])
        self.assertEqual(len(shelf.subshelves), 1)
        self.assertEqual(len(shelf.subshelves[0].nodes), 1)
        self.assertEqual(len(flatten_shelf(shelf)[0]), 1)
