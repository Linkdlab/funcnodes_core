import unittest
import funcnodes_core as fn
from typing import Tuple
import sys

if not sys.warnoptions:
    import warnings

    warnings.simplefilter("error", DeprecationWarning)


fn.config.IN_NODE_TEST = True


class TestDecorator(unittest.IsolatedAsyncioTestCase):
    async def test_update_value_options_decorator(self):
        @fn.NodeDecorator(
            "test_decorator_update_value",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": fn.decorator.update_other_io_options(
                            "key", lambda x: list(x.keys())
                        )
                    }
                }
            },
        )
        def select(obj: dict, key: str):
            return obj[key]

        node = select()

        self.assertEqual(
            len(node.inputs),
            3,
            f"Node should have 3 inputs: obj,key and _triggerinput, but has {node.inputs.keys()}.",
        )

        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key"], "value_options"),
            "Node-key has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key"].value_options,
            "Node-key has no value_options.options attribute.",
        )
        self.assertEqual(node["key"].value_options["options"], ["key1", "key2"])

    async def test_node_input_param(self):
        called_node = []

        @fn.NodeDecorator(
            "test_node_input_param",
            description="Test decorator for node param",
        )
        def select(a: int, node: fn.Node) -> int:
            called_node.append(node)
            return a + 1

        node = select()

        self.assertEqual(
            len(node.inputs),
            2,
            f"Node should have 3 inputs: a and _triggerinput, but has {node.inputs.keys()}.",
        )

        node["a"] = 1

        await node

        self.assertEqual(node.outputs["out"].value, 2)
        self.assertEqual(len(called_node), 1)
        self.assertEqual(called_node[0], node)

    async def test_update_multiple_value_options_decorator(self):
        @fn.NodeDecorator(
            "test_update_multiple_value_decorator",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": [
                            fn.decorator.update_other_io_options(
                                "key1", lambda x: list(x.keys())
                            ),
                            fn.decorator.update_other_io_options(
                                "key2", lambda x: list(x.keys()) + list(x.keys())
                            ),
                        ],
                    }
                }
            },
        )
        def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
            return obj[key1], obj[key2]

        node = select()
        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key1"], "value_options"),
            "Node-key1 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key1"].value_options,
            "Node-key1 has no value_options.options attribute.",
        )
        self.assertEqual(node["key1"].value_options["options"], ["key1", "key2"])

        self.assertTrue(
            hasattr(node["key2"], "value_options"),
            "Node-key2 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key2"].value_options,
            "Node-key2 has no value_options.options attribute.",
        )

        self.assertEqual(
            node["key2"].value_options["options"], ["key1", "key2", "key1", "key2"]
        )

    async def test_update_multiple_value_options_with_one_decorator(self):
        @fn.NodeDecorator(
            "test_update_multiple_value_with_one_decorator",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": fn.decorator.update_other_io_options(
                            ["key1", "key2"], lambda x: list(x.keys())
                        ),
                    }
                }
            },
        )
        def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
            return obj[key1], obj[key2]

        node = select()
        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key1"], "value_options"),
            "Node-key1 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key1"].value_options,
            "Node-key1 has no value_options.options attribute.",
        )
        self.assertEqual(node["key1"].value_options["options"], ["key1", "key2"])

        self.assertTrue(
            hasattr(node["key2"], "value_options"),
            "Node-key2 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key2"].value_options,
            "Node-key2 has no value_options.options attribute.",
        )

        self.assertEqual(node["key2"].value_options["options"], ["key1", "key2"])

    async def test_update_other_io_value_options(self):
        @fn.NodeDecorator(
            "test_decorator_update_value",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": fn.decorator.update_other_io_value_options(
                            "key", lambda x: {"options": list(x.keys())}
                        )
                    }
                }
            },
        )
        def select(obj: dict, key: str):
            return obj[key]

        node = select()
        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key"], "value_options"),
            "Node-key has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key"].value_options,
            "Node-key has no value_options.options attribute.",
        )
        self.assertEqual(node["key"].value_options["options"], ["key1", "key2"])

    async def test_update_other_io_value_options_multiple_calls(self):
        @fn.NodeDecorator(
            "test_update_multiple_value_decorator",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": [
                            fn.decorator.update_other_io_value_options(
                                "key1", lambda x: {"options": list(x.keys())}
                            ),
                            fn.decorator.update_other_io_value_options(
                                "key2",
                                lambda x: {"options": list(x.keys()) + list(x.keys())},
                            ),
                        ],
                    }
                }
            },
        )
        def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
            return obj[key1], obj[key2]

        node = select()
        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key1"], "value_options"),
            "Node-key1 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key1"].value_options,
            "Node-key1 has no value_options.options attribute.",
        )
        self.assertEqual(node["key1"].value_options["options"], ["key1", "key2"])

        self.assertTrue(
            hasattr(node["key2"], "value_options"),
            "Node-key2 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key2"].value_options,
            "Node-key2 has no value_options.options attribute.",
        )

        self.assertEqual(
            node["key2"].value_options["options"], ["key1", "key2", "key1", "key2"]
        )

    async def test_update_other_io_value_options_multiple_multipleios(self):
        @fn.NodeDecorator(
            "test_update_multiple_value_with_one_decorator",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": fn.decorator.update_other_io_value_options(
                            ["key1", "key2"], lambda x: {"options": list(x.keys())}
                        ),
                    }
                }
            },
        )
        def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
            return obj[key1], obj[key2]

        node = select()
        node["obj"] = {"key1": "value1", "key2": "value2"}
        await node

        self.assertTrue(
            hasattr(node["key1"], "value_options"),
            "Node-key1 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key1"].value_options,
            "Node-key1 has no value_options.options attribute.",
        )
        self.assertEqual(node["key1"].value_options["options"], ["key1", "key2"])

        self.assertTrue(
            hasattr(node["key2"], "value_options"),
            "Node-key2 has no value_options attribute.",
        )
        self.assertTrue(
            "options" in node["key2"].value_options,
            "Node-key2 has no value_options.options attribute.",
        )

        self.assertEqual(node["key2"].value_options["options"], ["key1", "key2"])
