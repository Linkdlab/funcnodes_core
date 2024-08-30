import unittest
import funcnodes_core as fn


class TestDecorator(unittest.IsolatedAsyncioTestCase):
    async def test_update_value_decorator(self):
        @fn.NodeDecorator(
            "test_decorator_update_value",
            description="Test decorator for updating value.",
            default_io_options={
                "obj": {
                    "on": {
                        "after_set_value": fn.decorator.update_other_io(
                            "key", lambda x: list(x.keys())
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
