import unittest
import time
from funcnodes_core.utils.nodeutils import (
    get_deep_connected_nodeset,
    run_until_complete,
)

from funcnodes_core.nodemaker import NodeDecorator

import funcnodes_core as fn
import asyncio

fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])


@NodeDecorator("dummy_nodefor testnodeutils")
async def identity(input: int) -> int:
    # add a little delay
    await asyncio.sleep(fn.node.NodeConstants.TRIGGER_SPEED_FAST * 1)
    return input


class TKNode(fn.Node):
    node_id = "tknode"
    ip1 = fn.NodeInput(uuid="ip1", type=int)
    ip2 = fn.NodeInput(uuid="ip2", type=int)

    op1 = fn.NodeOutput(uuid="op1", type=int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputs["op1"].value = 0

    async def func(self, ip1, ip2):
        self.outputs["op1"].value += 1


class TestNodeUtils(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create mock nodes with output connections to simulate a graph.
        self.node1 = identity()
        self.node2 = identity()
        self.node3 = identity()
        # Create connections between nodes.
        self.node1.outputs["out"].connect(self.node2.inputs["input"])
        self.node2.outputs["out"].connect(self.node3.inputs["input"])
        self.node1.inputs["input"].value = 10

    async def test_get_deep_connected_nodeset(self):
        # Test the deep collection of connected nodes.
        nodeset = get_deep_connected_nodeset(self.node1)
        self.assertIn(self.node1, nodeset)
        self.assertIn(self.node2, nodeset)
        self.assertIn(self.node3, nodeset)

    async def test_get_deep_connected_nodeset_with_node_in(self):
        nodeset = get_deep_connected_nodeset(self.node1, {self.node2})
        self.assertIn(self.node1, nodeset)
        self.assertIn(self.node2, nodeset)
        self.assertNotIn(self.node3, nodeset)

        nodeset = get_deep_connected_nodeset(self.node1, {self.node1})
        self.assertIn(self.node1, nodeset)
        self.assertNotIn(self.node2, nodeset)
        self.assertNotIn(self.node3, nodeset)

    async def test_run_until_complete_all_triggered(self):
        # Run the function until all nodes are no longer triggering.
        await run_until_complete(self.node1, self.node2, self.node3)
        self.assertEqual(self.node1.outputs["out"].value, 10)
        self.assertEqual(self.node2.outputs["out"].value, 10)
        self.assertEqual(self.node3.outputs["out"].value, 10)

    async def test_node_progress(self):
        # Test that the progress is updated as expected.
        collected = []

        def progress_callback(src, info, *args, **kwargs):
            collected.append(
                info,
            )

        await self.node1
        self.node1.on("progress", progress_callback)

        await self.node1

        self.assertEqual(
            len(collected),
            2,
            f"There should be two progress updates. One for triggering and one for idle. {collected}",
        )
        self.assertEqual(
            collected[0]["prefix"],
            "triggering",
            "The prefix should be 'triggering'.",
        )
        self.assertEqual(
            collected[1]["prefix"],
            "idle",
            "The prefix should be 'idle'.",
        )

    async def test_trigger_conut(self):
        node = TKNode(pretrigger_delay=0.1)
        await node
        self.assertEqual(node.outputs["op1"].value, 0)
        node.inputs["ip1"].value = 1
        node.inputs["ip2"].value = 2
        await node
        self.assertEqual(node.outputs["op1"].value, 1)

        import asyncio

        ts1 = time.time()

        for i in range(10):
            await node
        te1 = time.time()
        tw1 = te1 - ts1
        self.assertLess(tw1, 2)
        self.assertEqual(node.outputs["op1"].value, 11)

        ts2 = time.time()
        for i in range(10):
            node.inputs["ip1"].value = i
            await node
        te2 = time.time()
        tw2 = te2 - ts2
        self.assertEqual(node.outputs["op1"].value, 21)
        self.assertLess(tw2, 2)

        while node.in_trigger:
            await asyncio.sleep(0.0)

        pt = node.outputs["op1"].value
        node.inputs["ip1"].value = pt
        ts3 = time.time()
        while node.in_trigger:
            await asyncio.sleep(0.01)
        te3 = time.time()

        tw3 = te3 - ts3
        self.assertLess(tw3, 0.2)
        self.assertEqual(node.outputs["op1"].value, 22)

        node.inputs["ip1"].value = 10
        await asyncio.sleep(0.2)  # the delay is large, trigger twice
        node.inputs["ip2"].value = 20
        await node
        self.assertEqual(node.outputs["op1"].value, 24)

        node.inputs["ip1"].value = 11
        await asyncio.sleep(0.05)  # the delay is small, trigger once
        node.inputs["ip2"].value = 21
        await node
        self.assertEqual(node.outputs["op1"].value, 25)

    async def test_trigger_fast(self):
        node = TKNode()
        node.pretrigger_delay = 0.0
        node.inputs["ip1"].value = 1
        node.inputs["ip2"].value = 2
        await node
        self.assertEqual(node.outputs["op1"].value, 1)

        ts1 = time.time()
        for i in range(100):
            await node
        te1 = time.time()
        tw1 = te1 - ts1
        self.assertLess(tw1, 0.5)
        self.assertEqual(node.outputs["op1"].value, 101)
