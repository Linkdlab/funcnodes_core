import unittest
from funcnodes_core import NodeSpace, Node, NodeInput, NodeOutput, Shelf
import gc

import funcnodes_core as fn
import json

fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])


class DummyNode(Node):
    node_id = "ns_dummy_node"
    node_name = "Dummy Node"
    myinput = NodeInput(id="input", type=int, default=1)
    myoutput = NodeOutput(id="output", type=int)

    async def func(self, input: int) -> int:
        return input


class DummyNode2(Node):
    node_id = "ns_dummy_node2"
    node_name = "Dummy Node2"
    myinput = NodeInput(id="input", type=int, default=1)
    myoutput = NodeOutput(id="output", type=int)

    async def func(self, input: int) -> int:
        return input


class TestNodeSpace(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.nodespace = NodeSpace()
        self.nodespace.lib.add_node(DummyNode, "basic")

    def test_add_shelf(self):
        dummy_shelf = Shelf(
            name="test",
            description="test",
            nodes=[DummyNode, DummyNode2],
            subshelves=[],
        )

        self.nodespace.add_shelf(dummy_shelf)
        self.assertIn(dummy_shelf, self.nodespace.lib.shelves)
        self.nodespace.add_node_instance(DummyNode2())
        self.nodespace.add_node_instance(DummyNode())

        self.nodespace.remove_shelf(dummy_shelf)
        self.assertNotIn(dummy_shelf, self.nodespace.lib.shelves)

        self.assertEqual(len(self.nodespace.nodes), 1)

    def test_add_node_instance(self):
        node = DummyNode()
        self.nodespace.add_node_instance(node)
        self.assertIn(node, self.nodespace.nodes)

    def test_add_node_by_id(self):
        node_id = "ns_dummy_node"
        nodeuuid = self.nodespace.add_node_by_id(node_id).uuid
        self.assertIn(nodeuuid, [node.uuid for node in self.nodespace.nodes])

    def test_get_node_by_id(self):
        node_id = "ns_dummy_node"
        nodeuuid = self.nodespace.add_node_by_id(node_id).uuid
        node = self.nodespace.get_node_by_id(nodeuuid)
        self.assertEqual(nodeuuid, node.uuid)
        self.assertEqual(node_id, node.node_id)

    def test_serialize_nodes(self):
        node = DummyNode()
        self.nodespace.add_node_instance(node)
        serialized_nodes = self.nodespace.serialize_nodes()
        self.assertEqual(len(serialized_nodes), 1)

    def test_deserialize_nodes(self):
        node = DummyNode()
        self.nodespace.add_node_instance(node)
        self.assertEqual(len(self.nodespace.nodes), 1)
        serialized_nodes = self.nodespace.serialize_nodes()

        self.nodespace.deserialize_nodes(serialized_nodes)
        self.assertEqual(len(self.nodespace.nodes), 1)

    def test_serialize(self):
        node = DummyNode()
        self.nodespace.add_node_instance(node)
        serialized_nodespace = self.nodespace.serialize()
        self.assertIn("nodes", serialized_nodespace)
        self.assertIn("edges", serialized_nodespace)
        self.assertIn("prop", serialized_nodespace)

    def test_deserialize(self):
        node = DummyNode()
        self.nodespace.add_node_instance(node)
        serialized_nodespace = self.nodespace.serialize()

        self.nodespace.deserialize(serialized_nodespace)
        self.assertEqual(len(self.nodespace.nodes), 1)

    def test_serialize_forward(self):
        node1 = DummyNode()
        node2 = DummyNode()
        node1["output"].connect(node2["input"])
        node2["input"].connect(node1["input"])
        self.nodespace.add_node_instance(node1)
        self.nodespace.add_node_instance(node2)
        serialized_nodespace = self.nodespace.serialize()
        print(serialized_nodespace)

        self.assertEqual(len(serialized_nodespace["edges"]), 2)

    def test_deserialize_forward(self):
        node1 = DummyNode()
        node2 = DummyNode()
        node3 = DummyNode()
        node1["output"].connect(node2["input"])
        node2["input"].connect(node3["input"])
        self.nodespace.add_node_instance(node1)
        self.nodespace.add_node_instance(node2)
        self.nodespace.add_node_instance(node3)
        serialized_nodespace = self.nodespace.serialize()

        self.nodespace.remove_node_instance(node1)
        self.nodespace.remove_node_instance(node2)
        self.nodespace.remove_node_instance(node3)

        self.nodespace.deserialize(serialized_nodespace)

        self.assertEqual(len(self.nodespace.nodes), 3)
        self.assertEqual(len(self.nodespace.edges), 2)

        node1 = self.nodespace.get_node_by_id(node1.uuid)
        node2 = self.nodespace.get_node_by_id(node2.uuid)
        node3 = self.nodespace.get_node_by_id(node3.uuid)

        self.assertEqual(node1["output"].connections[0].node, node2)

        node1["output"].set_value(123)

        self.assertEqual(node3["input"].value, 123)

    def test_remove_node(self):
        gc.collect()
        # gc.set_debug(gc.DEBUG_LEAK)
        node1 = DummyNode()
        node2 = DummyNode()

        self.nodespace.add_node_instance(node1)
        self.nodespace.add_node_instance(node2)
        self.assertEqual(len(self.nodespace.nodes), 2)
        self.assertEqual(
            len(gc.get_referrers(node1)),
            5,
            "\n".join([f"{type(r)}:{r}" for r in gc.get_referrers(node1)]),
        )  # 5 because of the
        # nodespace,
        # the input
        # the output
        # io event listener (_triggerinput as additional input)
        # progress broadcast

        self.assertTrue(
            self.nodespace._nodes in gc.get_referrers(node1),
            gc.get_referrers(node1),
        )
        self.nodespace.remove_node_by_id(self.nodespace.nodes[0].uuid)
        self.assertEqual(len(self.nodespace.nodes), 1)

        # gollect garbage before node is deleted
        gc.collect()
        # delete node
        node1.__del__()

        # make sure node has no references
        self.assertEqual(len(gc.get_referrers(node1)), 0, gc.get_referrers(node1))

        # call del on node1 again to make sure it is out of scope
        del node1

        # # collect garbage
        # gc.collect()

        # # list all garbage
        # garb = gc.garbage

        # # disable debug
        # gc.set_debug(0)

        # # make sure there is no garbage
        # self.assertEqual(garb, [])

    def test_set_secret_prop(self):
        self.nodespace.set_secret_property("test", "test")
        ser = json.dumps(self.nodespace.serialize())
        assert "test" not in ser
        assert self.nodespace.get_property("test") == "test"
        self.nodespace.set_property("test", "test", secret=True)
        ser = json.dumps(self.nodespace.serialize())
        assert "test" not in ser
        self.nodespace.set_property("test", "test")
        ser = json.dumps(self.nodespace.serialize())
        assert "test" in ser

        self.nodespace.remove_property("test", ignore_public=True)

        assert self.nodespace.get_property("test") == "test"
        assert self.nodespace.get_secret_property("test") is None
        self.nodespace.remove_property("test")
        assert self.nodespace.get_property("test") is None
